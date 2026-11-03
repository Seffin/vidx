import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional, Tuple, Union, List
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
    end_screen_video: Optional[str] = None
    end_screen_duration: Optional[float] = None
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
    # Intro and outro offsets for bumpers
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


def outro_duration_seconds(config) -> float:
    """Seconds of outro/end-screen appended after narration ends.

    Used by chapter marker generator so conclusion markers can be validated
    against YouTube's 10-second minimum duration rule.
    """
    if not config:
        return 0.0
    bumpers_cfg = config.get("bumpers", {}) or {}
    total = 0.0
    ov = bumpers_cfg.get("outro_video")
    if ov:
        if isinstance(ov, (list, tuple)):
            for p in ov:
                if Path(p).exists():
                    total += get_media_duration(str(p))
        elif Path(ov).exists():
            total += get_media_duration(str(ov))
    es = bumpers_cfg.get("end_screen_video") or bumpers_cfg.get("endscreen_video")
    es_dur = bumpers_cfg.get("end_screen_duration") or bumpers_cfg.get("endscreen_duration")
    if es and Path(es).exists():
        p_es = Path(es)
        ov_list = [Path(x) for x in ov] if isinstance(ov, (list, tuple)) else ([Path(ov)] if ov else [])
        if p_es not in ov_list:
            if es_dur:
                total += float(es_dur)
            else:
                total += get_media_duration(str(es))
    if total > 0.0:
        return total
    oa = bumpers_cfg.get("outro_audio")
    if oa and Path(oa).exists():
        return get_media_duration(str(oa))
    video_cfg = config.get("video", {}) or {}
    if video_cfg.get("outro_image") or bumpers_cfg.get("outro_image"):
        return float(
            video_cfg.get("outro_duration") or bumpers_cfg.get("outro_duration") or 3.0
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
    outro_video: Optional[Union[str, List[str]]] = None,
    end_screen_video: Optional[str] = None,
    target_resolution: str = "1920x1080",
    fps: int = 24,
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    crf: int = 23,
    preset: str = "fast",
    end_screen_duration: Optional[float] = None,
    outro_duration: Optional[float] = None,
) -> Tuple[bool, float]:
    """
    Concatenate intro_video + main_video + outro_videos into output_video using FFmpeg.
    Supports sequence: intro + main + end + end_screen (or multiple outro clips).
    Automatically synthesizes a silent audio track for clips that have no audio stream,
    ensuring seamless multi-clip concatenation without audio sync failure.

    Returns: (success: bool, intro_duration_sec: float)
    """
    main_path = Path(main_video)
    out_path = Path(output_video)

    if not main_path.exists():
        print(f"[!] Video bumper concat: main video not found: {main_path}")
        return False, 0.0

    intro_path = Path(intro_video) if intro_video else None
    has_intro = intro_path is not None and intro_path.exists()

    # Collect all outro / ending video paths in order
    outro_paths = []
    if outro_video:
        if isinstance(outro_video, (list, tuple)):
            for ov in outro_video:
                p = Path(ov)
                if p.exists():
                    outro_paths.append(p)
        else:
            p = Path(outro_video)
            if p.exists():
                outro_paths.append(p)

    if end_screen_video:
        p = Path(end_screen_video)
        if p.exists() and p not in outro_paths:
            outro_paths.append(p)

    if not has_intro and not outro_paths:
        # Nothing to do — copy in place if paths differ
        if str(main_path.resolve()) != str(out_path.resolve()):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(main_path), str(out_path))
        return True, 0.0

    intro_dur = get_media_duration(str(intro_path)) if has_intro else 0.0
    intro_label = f"YES ({round(intro_dur, 1)}s)" if has_intro else "NO"
    def _get_outro_len(p: Path) -> float:
        if end_screen_video and p == Path(end_screen_video) and end_screen_duration:
            return float(end_screen_duration)
        if outro_duration and outro_video and p == Path(outro_video):
            return float(outro_duration)
        return get_media_duration(str(p))

    outro_labels = ", ".join(f"{p.name} ({round(_get_outro_len(p), 1)}s)" for p in outro_paths) if outro_paths else "NO"
    print(f"[*] Video bumper: intro={intro_label}, outros=[{outro_labels}]")

    # Parse target resolution
    try:
        tw, th = map(int, target_resolution.split("x"))
    except Exception:
        tw, th = 1920, 1080

    scale_filter = (
        f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
        f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
    )

    tmp_dir = out_path.parent / ".bumper_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    def has_audio_stream(filepath: Path) -> bool:
        """Check if media file contains an audio stream."""
        try:
            res = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(filepath)],
                capture_output=True, text=True, check=True
            )
            return bool(res.stdout.strip())
        except Exception:
            return False

    def normalize_clip(src: Path, dst: Path, duration: Optional[float] = None) -> bool:
        """Re-encode a clip to common resolution/fps/codec so FFmpeg concat works.
        Adds silent audio if source file has no audio stream."""
        has_a = has_audio_stream(src)
        dur_args = ["-t", str(duration)] if duration else []
        if has_a:
            norm_cmd = [
                "ffmpeg", "-y",
                *dur_args,
                "-i", str(src),
                "-vf", scale_filter,
                "-c:v", video_codec,
                "-preset", preset,
                "-crf", str(crf),
                "-c:a", audio_codec,
                "-ar", "48000",
                "-ac", "2",
                *dur_args,
                str(dst),
            ]
        else:
            # Source is silent/video-only: synthesize silent stereo audio matching video duration
            norm_cmd = [
                "ffmpeg", "-y",
                *dur_args,
                "-i", str(src),
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-vf", scale_filter,
                "-c:v", video_codec,
                "-preset", preset,
                "-crf", str(crf),
                "-c:a", audio_codec,
                "-shortest",
                *dur_args,
                str(dst),
            ]
        res = subprocess.run(norm_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            print(f"[!] Bumper normalisation failed for {src.name}:")
            print(res.stderr.decode("utf-8", errors="replace")[-800:])
        return res.returncode == 0 and dst.exists()

    clip_paths = []

    # 1. Intro
    if has_intro:
        norm_intro = tmp_dir / ("intro_norm" + intro_path.suffix)
        if normalize_clip(intro_path, norm_intro):
            clip_paths.append(str(norm_intro))
        else:
            print("[!] Skipping intro video — normalisation failed.")

    # 2. Main scripture video
    norm_main = tmp_dir / ("main_norm" + main_path.suffix)
    if normalize_clip(main_path, norm_main):
        clip_paths.append(str(norm_main))
    else:
        print("[!] Main video normalisation failed — using original.")
        clip_paths.append(str(main_path))

    # 3. Outros (e.g. End.mp4 + end screen.mp4)
    for idx, op in enumerate(outro_paths):
        norm_outro = tmp_dir / f"outro_{idx}_norm{op.suffix}"
        dur = None
        if end_screen_video and op == Path(end_screen_video) and end_screen_duration:
            dur = float(end_screen_duration)
        elif outro_duration and outro_video and op == Path(outro_video):
            dur = float(outro_duration)
        if normalize_clip(op, norm_outro, duration=dur):
            clip_paths.append(str(norm_outro))
        else:
            print(f"[!] Skipping outro video {op.name} — normalisation failed.")

    if len(clip_paths) == 1 and clip_paths[0] == str(main_path):
        if str(main_path.resolve()) != str(out_path.resolve()):
            shutil.copyfile(str(main_path), str(out_path))
        return True, intro_dur

    # Write FFmpeg concat list file with resolved absolute paths and forward slashes
    concat_list = tmp_dir / "concat_list.txt"
    with open(concat_list, "w", encoding="utf-8") as cf:
        for cp in clip_paths:
            abs_posix = Path(cp).resolve().as_posix()
            safe = abs_posix.replace("'", "'\\''")
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
    clip_names = " + ".join([Path(c).name for c in clip_paths])
    print(f"[*] Concatenating {len(clip_paths)} clips ({clip_names}) into: {out_path.name}")
    res = subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ok = res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0
    if not ok:
        print("[!] Video concat failed:")
        print(res.stderr.decode("utf-8", errors="replace")[-800:])

    # Cleanup temp normalised clips
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
