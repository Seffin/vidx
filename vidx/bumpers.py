import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

try:
    import mutagen
except ImportError:
    mutagen = None


@dataclass
class BumperConfig:
    intro_audio: Optional[str] = None
    outro_audio: Optional[str] = None
    intro_video: Optional[str] = None
    outro_video: Optional[str] = None
    title_image: Optional[str] = None
    outro_image: Optional[str] = None
    title_duration: Optional[float] = None
    outro_duration: Optional[float] = None
    background_music: Optional[str] = None
    background_music_volume: float = 0.15


def intro_offset_seconds(config) -> float:
    """Seconds of intro prepended before verse 1, so timestamps can be shifted.

    Anything derived from timing data -- subtitles, YouTube chapter markers --
    must apply the same offset or it points at the wrong moment. `config` is the
    raw config dict.
    """
    if not config:
        return 0.0
    bumpers_cfg = config.get("bumpers", {}) or {}
    video_cfg = config.get("video", {}) or {}
    # written by the render path once the real intro video/audio has been built
    if "_calc_intro_duration" in bumpers_cfg:
        return float(bumpers_cfg["_calc_intro_duration"])
    # Video intro takes priority over audio intro for offset calculation
    intro_vid = bumpers_cfg.get("intro_video")
    if intro_vid and Path(intro_vid).exists():
        return get_media_duration(intro_vid)
    intro = bumpers_cfg.get("intro_audio")
    if intro and Path(intro).exists():
        return get_media_duration(intro)
    if video_cfg.get("title_image") or bumpers_cfg.get("title_image"):
        return float(
            video_cfg.get("title_duration") or bumpers_cfg.get("title_duration") or 3.0
        )
    return 0.0


def get_media_duration(file_path: str) -> float:
    """Get duration of audio or video media file in seconds."""
    path = Path(file_path)
    if not path.exists():
        return 0.0

    # 1. Try mutagen
    if mutagen is not None:
        try:
            audio = mutagen.File(str(path))
            if (
                audio is not None
                and hasattr(audio, "info")
                and hasattr(audio.info, "length")
                and audio.info.length > 0
            ):
                return float(audio.info.length)
        except Exception:
            pass

    # 2. Try ffprobe
    try:
        res = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            check=True,
        )
        val = res.stdout.strip()
        if val:
            return float(val)
    except Exception:
        pass

    # 3. Try wave module for wav files
    try:
        if path.suffix.lower() == ".wav":
            with wave.open(str(path), "r") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return float(frames) / float(rate)
    except Exception:
        pass

    return 0.0


def prepare_bumper_audio(
    main_audio: str,
    output_audio: str,
    intro_audio: Optional[str] = None,
    outro_audio: Optional[str] = None,
    background_music: Optional[str] = None,
    bg_music_volume: float = 0.15,
) -> Tuple[bool, float, float]:
    """
    Concatenate intro_audio + main_audio + outro_audio into output_audio,
    optionally mixing looped background_music along with main_audio.
    Returns: (success: bool, intro_duration_sec: float, total_duration_sec: float)
    """
    main_path = Path(main_audio)
    out_path = Path(output_audio)

    if not main_path.exists():
        return False, 0.0, 0.0

    intro_path = Path(intro_audio) if intro_audio else None
    outro_path = Path(outro_audio) if outro_audio else None
    bgm_path = Path(background_music) if background_music else None

    has_intro = intro_path is not None and intro_path.exists()
    has_outro = outro_path is not None and outro_path.exists()
    has_bgm = bgm_path is not None and bgm_path.exists()

    intro_dur = get_media_duration(str(intro_path)) if has_intro else 0.0

    # If no bumpers or BGM needed, simply copy or point to main audio
    if not has_intro and not has_outro and not has_bgm:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if str(main_path.resolve()) != str(out_path.resolve()):
            shutil.copyfile(str(main_path), str(out_path))
        return True, 0.0, get_media_duration(str(out_path))

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Build FFmpeg filter complex command
    inputs = []
    filter_parts = []
    idx = 0

    intro_label = None
    if has_intro:
        inputs.extend(["-i", str(intro_path)])
        intro_label = f"[{idx}:0]"
        idx += 1

    inputs.extend(["-i", str(main_path)])
    main_label = f"[{idx}:0]"
    idx += 1

    if has_bgm:
        inputs.extend(["-stream_loop", "-1", "-i", str(bgm_path)])
        bgm_label = f"[{idx}:0]"
        idx += 1
        mix_label = "[main_mixed]"
        filter_parts.append(
            f"{bgm_label}volume={bg_music_volume}[bgm_vol];{main_label}[bgm_vol]amix=inputs=2:duration=first:normalize=0{mix_label};"
        )
        current_main = mix_label
    else:
        current_main = main_label

    outro_label = None
    if has_outro:
        inputs.extend(["-i", str(outro_path)])
        outro_label = f"[{idx}:0]"
        idx += 1

    if has_intro or has_outro:
        concat_inputs = []
        if has_intro:
            concat_inputs.append(intro_label)
        concat_inputs.append(current_main)
        if has_outro:
            concat_inputs.append(outro_label)
        n_concat = len(concat_inputs)
        filter_parts.append(
            "".join(concat_inputs) + f"concat=n={n_concat}:v=0:a=1[outa]"
        )
        map_target = "[outa]"
    else:
        map_target = current_main

    filter_str = "".join(filter_parts).rstrip(";")
    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        filter_str,
        "-map",
        map_target,
        str(out_path),
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and out_path.exists():
            total_dur = get_media_duration(str(out_path))
            return True, intro_dur, total_dur
        else:
            return False, intro_dur, 0.0
    except Exception:
        return False, intro_dur, 0.0

def concat_video_bumpers(
    main_video: str,
    output_video: str,
    intro_video: Optional[str] = None,
    outro_video: Optional[str] = None,
    target_resolution: str = "1920x1080",
    fps: int = 24,
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    crf: int = 23,
    preset: str = "fast",
) -> Tuple[bool, float]:
    """
    Concatenate intro_video + main_video + outro_video into output_video using FFmpeg.

    All clips are re-encoded to a common resolution/fps/codec so the concat filter
    works reliably even when the intro/outro resolution differs from the scripture video.

    Returns: (success: bool, intro_duration_sec: float)
    """
    main_path = Path(main_video)
    out_path = Path(output_video)

    if not main_path.exists():
        print(f"[!] Video bumper concat: main video not found: {main_path}")
        return False, 0.0

    intro_path = Path(intro_video) if intro_video else None
    outro_path = Path(outro_video) if outro_video else None

    has_intro = intro_path is not None and intro_path.exists()
    has_outro = outro_path is not None and outro_path.exists()

    if not has_intro and not has_outro:
        # Nothing to do — copy in place if paths differ
        if str(main_path.resolve()) != str(out_path.resolve()):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(main_path), str(out_path))
        return True, 0.0

    intro_dur = get_media_duration(str(intro_path)) if has_intro else 0.0
    intro_label = f"YES ({round(intro_dur, 1)}s)" if has_intro else "NO"
    outro_label = "YES" if has_outro else "NO"
    print(f"[*] Video bumper: intro={intro_label}, outro={outro_label}")

    # Parse target resolution
    try:
        tw, th = map(int, target_resolution.split("x"))
    except Exception:
        tw, th = 1920, 1080

    scale_filter = (
        f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
        f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
    )

    # Use a temporary directory for intermediate normalised clips
    tmp_dir = out_path.parent / ".bumper_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    def normalize_clip(src: Path, dst: Path) -> bool:
        """Re-encode a clip to common resolution/fps/codec so FFmpeg concat works."""
        norm_cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-vf", scale_filter,
            "-c:v", video_codec,
            "-preset", preset,
            "-crf", str(crf),
            "-c:a", audio_codec,
            "-ar", "48000",
            "-ac", "2",
            str(dst),
        ]
        res = subprocess.run(norm_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            print(f"[!] Bumper normalisation failed for {src.name}:")
            print(res.stderr.decode("utf-8", errors="replace")[-800:])
        return res.returncode == 0 and dst.exists()

    # Build list of clips to concatenate
    clip_paths = []

    if has_intro:
        norm_intro = tmp_dir / ("intro_norm" + intro_path.suffix)
        if normalize_clip(intro_path, norm_intro):
            clip_paths.append(str(norm_intro))
        else:
            print("[!] Skipping intro video — normalisation failed.")

    # Main scripture video — normalise so codec/resolution matches bumpers
    norm_main = tmp_dir / ("main_norm" + main_path.suffix)
    if normalize_clip(main_path, norm_main):
        clip_paths.append(str(norm_main))
    else:
        print("[!] Main video normalisation failed — using original.")
        clip_paths.append(str(main_path))

    if has_outro:
        norm_outro = tmp_dir / ("outro_norm" + outro_path.suffix)
        if normalize_clip(outro_path, norm_outro):
            clip_paths.append(str(norm_outro))
        else:
            print("[!] Skipping outro video — normalisation failed.")

    if len(clip_paths) == 1 and clip_paths[0] == str(main_path):
        # Nothing useful was added — just copy
        if str(main_path.resolve()) != str(out_path.resolve()):
            shutil.copyfile(str(main_path), str(out_path))
        return True, intro_dur

    # Write FFmpeg concat list file
    concat_list = tmp_dir / "concat_list.txt"
    with open(concat_list, "w", encoding="utf-8") as cf:
        for cp in clip_paths:
            # FFmpeg concat list requires absolute paths with forward slashes
            abs_posix = Path(cp).resolve().as_posix()
            safe = abs_posix.replace("'", "'\''")
            cf.write(f"file '{safe}'\n")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    concat_cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(out_path),
    ]
    print(f"[*] Concatenating {len(clip_paths)} clips into: {out_path.name}")
    res = subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ok = res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0
    if not ok:
        print("[!] Video concat failed:")
        print(res.stderr.decode("utf-8", errors="replace")[-800:])

    # Cleanup temp normalised clips (keep concat_list for debugging)
    try:
        for p in tmp_dir.iterdir():
            if p.name != "concat_list.txt":
                try:
                    p.unlink()
                except Exception:
                    pass
    except Exception:
        pass

    return ok, intro_dur
