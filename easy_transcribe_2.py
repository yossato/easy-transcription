import tkinter as tk
from tkinter import filedialog
import subprocess
import os
import tempfile
import pathlib
import re
import threading
import pyaudio
import wave

# WhisperKitのモデルへのパスを環境に合わせて書き換えてください
MODEL = "/Users/yoshiaki/Projects/whisperkit/Models/whisperkit-coreml/openai_whisper-large-v3-v20240930_626MB"

# --- 録音用のグローバル変数 ---
is_recording = False
recording_thread = None
frames = []  # 録音データを保持するリスト

def record_loop():
    """
    pyaudio を利用して、16kHz、モノラル、16ビットの音声を連続して読み込みます。
    is_recording が False になるまでループし、フレームはグローバル変数 frames に格納されます。
    """
    global is_recording, frames
    CHUNK = 1024
    FORMAT = pyaudio.paInt16  # 16ビット
    CHANNELS = 1             # モノラル
    RATE = 16000             # 16kHz
    pa = pyaudio.PyAudio()
    stream = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                     input=True, frames_per_buffer=CHUNK)
    frames = []
    while is_recording:
        try:
            data = stream.read(CHUNK)
        except Exception as e:
            break
        frames.append(data)
    stream.stop_stream()
    stream.close()
    pa.terminate()

def toggle_recording():
    """
    録音開始/停止のトグル動作を実現します。
    録音開始時はバックグラウンドスレッドで音声を録音し、
    録音停止時は録音を終了、wavファイルとして一時ディレクトリに保存し、
    whisperkit-cli により文字起こしを行います。
    """
    global is_recording, recording_thread, frames
    if not is_recording:
        # 録音開始
        is_recording = True
        record_button.config(text="録音停止")
        recording_thread = threading.Thread(target=record_loop)
        recording_thread.start()
    else:
        # 録音停止
        is_recording = False
        record_button.config(text="録音開始")
        recording_thread.join()  # 録音スレッドの終了を待つ

        # 一時ディレクトリ内に録音結果を WAV ファイルとして保存
        with tempfile.TemporaryDirectory() as temp_dir:
            wav_file = os.path.join(temp_dir, "recorded.wav")
            wf = wave.open(wav_file, 'wb')
            wf.setnchannels(1)
            # 16ビットなのでサンプルサイズは 2 バイト
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"".join(frames))
            wf.close()

            # whisperkit-cli を実行して文字起こし
            whisperkit_cmd = [
                "whisperkit-cli",
                "transcribe",
                "--audio-path", wav_file,
                "--model-path", MODEL,
                "--language", "ja",
                "--report",
                "--report-path", temp_dir
            ]
            try:
                subprocess.run(whisperkit_cmd, check=True)
            except subprocess.CalledProcessError as e:
                result_label.config(text=f"whisperkit-cliの実行でエラーが発生しました: {e}")
                return

            # 出力された SRT ファイルを読み込み、不要な行・タグを削除する処理
            srt_file = os.path.join(temp_dir, "recorded.srt")
            if os.path.exists(srt_file):
                with open(srt_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                processed_lines = []
                for line in lines:
                    line = line.rstrip("\n")
                    # 行が数字のみの場合（字幕番号）を除去
                    if re.match(r'^\d+$', line.strip()):
                        continue
                    # タイムスタンプ行を除去（例: 00:00:01,000 --> 00:00:04,000）
                    if re.match(r'^\d{2}:\d{2}:\d{2},\d{3} -->', line):
                        continue
                    # <|...|> で囲まれたタグ部分を除去
                    line = re.sub(r'<\|[^|]+\|>', '', line)
                    if not line.strip():
                        continue
                    processed_lines.append(line)
                transcript = "\n".join(processed_lines)
                # 改行コードを LF から CR に変換（Notes アプリ用）
                processed_transcript = transcript.replace("\n", "\r")
                result_label.config(text=processed_transcript)
            else:
                result_label.config(text="SRTファイルが見つかりませんでした。")

def transcribe_audio():
    """
    既存の音声ファイル選択→変換→文字起こし処理
    """
    audio_file = filedialog.askopenfilename(
        filetypes=[
            ("音声ファイル", "*.wav *.mp3 *.m4a *.flac *.aac *.ogg *.mov *.mp4"),
            ("すべてのファイル", "*.*")
        ]
    )
    if not audio_file:
        return

    basename = pathlib.Path(audio_file).stem
    with tempfile.TemporaryDirectory() as temp_dir:
        wav_file = os.path.join(temp_dir, f"{basename}.wav")
        # ffmpeg で 16kHz, モノラル, PCM(WAV) に変換
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", audio_file,
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            wav_file,
            "-y"
        ]
        subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        whisperkit_cmd = [
            "whisperkit-cli",
            "transcribe",
            "--audio-path", wav_file,
            "--model-path", MODEL,
            "--language", "ja",
            "--report",
            "--report-path", temp_dir
        ]
        try:
            subprocess.run(whisperkit_cmd, check=True)
        except subprocess.CalledProcessError as e:
            result_label.config(text=f"whisperkit-cliの実行でエラーが発生しました: {e}")
            return

        srt_file = os.path.join(temp_dir, f"{basename}.srt")
        if os.path.exists(srt_file):
            with open(srt_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            processed_lines = []
            for line in lines:
                line = line.rstrip("\n")
                if re.match(r'^\d+$', line.strip()):
                    continue
                if re.match(r'^\d{2}:\d{2}:\d{2},\d{3} -->', line):
                    continue
                line = re.sub(r'<\|[^|]+\|>', '', line)
                if not line.strip():
                    continue
                processed_lines.append(line)
            transcript = "\n".join(processed_lines)
            processed_transcript = transcript.replace("\n", "\r")
            result_label.config(text=processed_transcript)
        else:
            result_label.config(text="SRTファイルが見つかりませんでした。")


# --- GUI 部分 ---
root = tk.Tk()
root.title("WhisperKit 文字起こしサンプル")

# 音声ファイル選択して文字起こし用ボタン
transcribe_button = tk.Button(root, text="音声ファイルを選択して文字起こし", command=transcribe_audio)
transcribe_button.pack(pady=10)

# 録音開始/停止用トグルボタン
record_button = tk.Button(root, text="録音開始", command=toggle_recording)
record_button.pack(pady=10)

# 文字起こし結果表示用ラベル
result_label = tk.Label(root, text="", justify="left", wraplength=600, bg="white", anchor="nw")
result_label.pack(padx=20, pady=20, fill="both", expand=True)

root.mainloop()
