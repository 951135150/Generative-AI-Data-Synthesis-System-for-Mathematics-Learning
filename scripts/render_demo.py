"""Align offline narration with real browser recording; burn Chinese subtitles."""
import argparse
import array
import json
import math
import re
import shutil
import subprocess
import sys
import textwrap
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def stamp(seconds, ass=False):
    units = int(round(seconds * (100 if ass else 1000)))
    base = 100 if ass else 1000
    whole, fraction = divmod(units, base)
    hours, rest = divmod(whole, 3600)
    minutes, sec = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{sec:02}.{fraction:02}" if ass else f"{hours:02}:{minutes:02}:{sec:02},{fraction:03}"


def wrap_caption(text, maximum=40):
    """Balance lines and prefer clause boundaries over splitting a Chinese word."""
    lines = []
    while len(text) > maximum:
        target = math.ceil(len(text) / math.ceil(len(text) / maximum))
        cuts = [i + 1 for i, char in enumerate(text[:maximum])
                if char in "，、；：" and i + 1 >= max(8, target - 12)]
        cut = min(cuts, key=lambda i: abs(i - target)) if cuts else target
        lines.append(text[:cut]); text = text[cut:]
    if text:
        lines.append(text)
    return lines


def audio_info(folder, narration_file):
    narration = read_json(narration_file)
    manifest = {}
    for scene in narration["scenes"]:
        with wave.open(str(folder / "voice" / f"{scene['id']}.wav"), "rb") as source:
            frames = source.readframes(source.getnframes())
            assert source.getsampwidth() == 2 and source.getnchannels() == 1
            samples = array.array("h", frames)
            rms = math.sqrt(sum(value * value for value in samples) / max(1, len(samples)))
            duration = source.getnframes() / source.getframerate()
            assert duration > 2 and rms > 10, "Narration must contain actual non-silent PCM audio."
            manifest[scene["id"]] = {"duration": duration, "rate": source.getframerate(), "rms": round(rms, 2)}
    (folder / "voice/manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"voice_scenes": len(manifest), "speech_seconds": round(sum(v["duration"] for v in manifest.values()), 1)}))


def render(folder):
    sys.path.insert(0, str(ROOT / ".runtime/video-tools"))
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    output = ROOT / "reports/demo" / folder.name
    report = read_json(output / "acceptance.json")
    narration = read_json(ROOT / report.get("narration_file", "data/evaluation/demo_narration.json"))
    english = narration["language"].startswith("en")
    assert report["completed"] is True, "Do not export a failed or incomplete recording."
    assert report["criticalErrors"] == [] and report["failedRequests"] == []
    assert len(report["timeline"]) == 11
    raw = Path(report["videoPath"])
    assert raw.is_file()
    manifest = read_json(folder / "voice/manifest.json")
    rate = next(iter(manifest.values()))["rate"]
    total = report["duration"] + .5
    audio = bytearray(math.ceil(total * rate) * 2)
    captions, srt, transcript = [], [], (["# Calculus Atelier — Project Demonstration\n"] if english else ["# 中文演示讲稿\n", "本地合成配音；真实网页操作；离线 AI 模拟；合成练习记录。\n"])
    cue = 1
    for scene in report["timeline"]:
        with wave.open(str(folder / "voice" / (scene["id"] + ".wav")), "rb") as source:
            assert source.getframerate() == rate
            pcm = source.readframes(source.getnframes())
        offset = round(scene["audio_start"] * rate) * 2
        assert offset + len(pcm) <= len(audio)
        audio[offset:offset + len(pcm)] = pcm
        # Each short spoken sentence gets a timed subtitle; estimated sentence
        # allocation is proportional to text length within the actual WAV duration.
        sentences = [s for s in re.split(r"(?<=[.!?])\s+" if english else r"(?<=[。！？])", scene["text"]) if s.strip()]
        length = sum(len(s) for s in sentences)
        cursor = scene["audio_start"]
        for sentence in sentences:
            duration = scene["audio_duration"] * len(sentence) / length
            end = cursor + duration
            lines = textwrap.wrap(sentence, width=94, break_long_words=False, break_on_hyphens=False) if english else wrap_caption(sentence)
            wrapped = r"\N".join(lines)
            captions.append(f"Dialogue: 0,{stamp(cursor, True)},{stamp(end, True)},Caption,,0,0,0,,{wrapped}")
            srt.append(f"{cue}\n{stamp(cursor)} --> {stamp(end)}\n" + "\n".join(lines) + "\n")
            cue += 1
            cursor = end
        captions.append(f"Dialogue: 1,{stamp(scene['start'], True)},{stamp(scene['end'], True)},Chapter,,0,0,0,,{scene['title']}")
        transcript.append(f"## {stamp(scene['start'])} · {scene['title']}\n\n{scene['text']}\n")
    wav = output / "narration.wav"
    with wave.open(str(wav), "wb") as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(rate); stream.writeframes(audio)
    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1600
PlayResY: 900
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Microsoft YaHei,32,&H00F9F7F0,&H00FFFFFF,&H00142439,&H00142439,0,0,0,0,100,100,0,0,1,0,0,2,70,70,14,1
Style: Chapter,Microsoft YaHei,20,&H00D7B577,&H00FFFFFF,&H00142439,&H00142439,0,0,0,0,100,100,0,0,1,0,0,1,25,25,76,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    if english:
        ass_header = ass_header.replace("Microsoft YaHei,32", "Segoe UI,29").replace("Microsoft YaHei,20", "Segoe UI,20")
    (output / "timeline.ass").write_text(ass_header + "\n".join(captions), encoding="utf-8-sig")
    (output / ("Calculus_Atelier_EN.srt" if english else "Calculus_Atelier_中文.srt")).write_text("\n".join(srt), encoding="utf-8-sig")
    (output / ("Narration_EN.md" if english else "讲稿.md")).write_text("\n".join(transcript), encoding="utf-8")
    target = output / ("Calculus_Atelier_Project_Demo_EN.mp4" if english else "Calculus_Atelier_中文演示.mp4")
    command = [ffmpeg, "-y", "-hide_banner", "-i", str(raw), "-i", str(wav),
               "-vf", "pad=iw:ih+100:0:0:color=0x142439,ass=timeline.ass", "-c:v", "libx264",
               "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
               "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-movflags", "+faststart", "-shortest", str(target)]
    with (output / "render.log").open("w", encoding="utf-8") as log:
        subprocess.run(command, cwd=output, stdout=log, stderr=log, check=True)
    silent = output / ("Calculus_Atelier_EN_Silent.mp4" if english else "Calculus_Atelier_字幕静音版.mp4")
    subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(target), "-c:v", "copy", "-an", str(silent)], check=True)
    # Decode the final file from start to end; metadata alone cannot catch a bad render.
    decoded = subprocess.run([ffmpeg, "-v", "error", "-i", str(target), "-f", "null", "-"], check=True, capture_output=True)
    assert not decoded.stderr.strip(), "Final video emitted decode errors."
    reader = imageio_ffmpeg.read_frames(str(target))
    metadata = next(reader)
    reader.close()
    assert metadata["size"] == (1600, 900)
    for scene in report["timeline"]:
        second = min(scene["audio_start"] + scene["audio_duration"] * .65, scene["end"] - .2)
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", str(second), "-i", str(target),
                        "-frames:v", "1", str(output / "screens" / (scene["id"] + "-final.png"))], check=True)
    final = {"file": str(target), "silent_file": str(silent), "width": 1600, "height": 900,
             "duration_seconds": round(metadata["duration"], 2), "size_mb": round(target.stat().st_size / 1024**2, 2),
             "voice": narration["voice"] + " (local synthetic speech)", "language": narration["language"],
             "subtitles": "Burned-in ASS plus UTF-8 SRT; sentence timing is estimated from each WAV.",
             "full_decode_check": "passed", "narration_non_silent": True,
             "note": "Recorded actual isolated application; runtime provenance is retained in acceptance.json."}
    (output / "delivery.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(final, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True, type=Path)
    parser.add_argument("--audio-info", action="store_true")
    parser.add_argument("--narration", type=Path, default=ROOT / "data/evaluation/demo_narration.json")
    args = parser.parse_args()
    demo_folder = args.folder.resolve()
    if not demo_folder.is_relative_to(ROOT / ".runtime/demo"):
        raise ValueError("Use an isolated demo folder.")
    audio_info(demo_folder, args.narration) if args.audio_info else render(demo_folder)
