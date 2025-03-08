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
import audioop

# WhisperKitのモデルへのパスを環境に合わせて書き換えてください
MODEL = "/Users/yoshiaki/Projects/whisperkit/Models/whisperkit-coreml/openai_whisper-large-v3-v20240930_626MB"

# グローバル変数
is_recording = False   # 録音中かどうかのフラグ
frames = []            # 録音中の音声データ（録音開始後にのみデータを追加）
current_level = 0      # 現在のマイク入力の音量（各チャンクの最大値）

# レベルメーターの見た目設定
METER_WIDTH = 300
METER_HEIGHT = 30
# レベルメーターの最大値（この値以上は飽和とみなす、環境に合わせて調整してください）
LEVEL_METER_MAX = 32767  # 16bit の最大値

def monitor_audio():
    """
    アプリ起動時から常にマイク入力を読み込み、各チャンクごとに
    audioop.max() を用いて 16bit のデータ中の最大値を計算し、current_level に更新します。
    録音中の場合は、そのデータも frames に追加します。
    """
    global current_level, frames, is_recording
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    pa = pyaudio.PyAudio()
    stream = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                     input=True, frames_per_buffer=CHUNK)
    while True:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
        except Exception:
            continue
        # 各チャンクの最大値を取得
        current_level = audioop.max(data, 2)
        if is_recording:
            frames.append(data)

def update_level_meter():
    """
    current_level の値をもとに、Canvas上にレベルメーターを更新します。
    LEVEL_METER_MAX を基準として [0,1] の比率に変換し、緑の矩形として描画します。
    """
    global current_level
    level_ratio = min(current_level / LEVEL_METER_MAX, 1.0)
    meter_fill_width = int(METER_WIDTH * level_ratio)
    meter_canvas.delete("all")
    meter_canvas.create_rectangle(0, 0, meter_fill_width, METER_HEIGHT, fill="green")
    meter_canvas.create_rectangle(0, 0, METER_WIDTH, METER_HEIGHT, outline="black")
    root.after(50, update_level_meter)

def toggle_recording():
    """
    録音開始/停止のトグル動作を実現します。
    録音開始時は frames をクリアし、フラグを True に設定。
    録音停止時はフラグを False にし、蓄積したデータを一時WAVファイルに保存後、
    whisperkit-cli による文字起こしを実行します。
    """
    global is_recording, frames
    if not is_recording:
        frames = []
        is_recording = True
        record_button.config(text="録音停止")
    else:
        is_recording = False
        record_button.config(text="録音開始")
        with tempfile.TemporaryDirectory() as temp_dir:
            wav_file = os.path.join(temp_dir, "recorded.wav")
            wf = wave.open(wav_file, 'wb')
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16ビット = 2バイト
            wf.setframerate(16000)
            wf.writeframes(b"".join(frames))
            wf.close()

            # whisperkit-cli で文字起こしを実行
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

            # 出力された SRT ファイルの読み込みと不要行・タグの削除
            srt_file = os.path.join(temp_dir, "recorded.srt")
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

def transcribe_audio():
    """
    ファイル選択による文字起こし処理。
    ユーザーが選択した音声ファイルを ffmpeg で 16kHz/モノラル/16bit の WAV に変換後、
    whisperkit-cli により文字起こしを実行します。
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

# --- GUI部分 ---
root = tk.Tk()
root.title("WhisperKit 文字起こしサンプル")

# 音声ファイル選択して文字起こし用ボタン
transcribe_button = tk.Button(root, text="音声ファイルを選択して文字起こし", command=transcribe_audio)
transcribe_button.pack(pady=10)

# 録音開始/停止用トグルボタン
record_button = tk.Button(root, text="録音開始", command=toggle_recording)
record_button.pack(pady=10)

# レベルメーター表示用キャンバス（録音していなくても常時表示）
meter_canvas = tk.Canvas(root, width=METER_WIDTH, height=METER_HEIGHT, bg="white")
meter_canvas.pack(pady=10)

# 文字起こし結果表示用ラベル
result_label = tk.Label(root, text="", justify="left", wraplength=600, bg="white", anchor="nw")
result_label.pack(padx=20, pady=20, fill="both", expand=True)

# マイクレベルの監視スレッド（常時動作）
monitor_thread = threading.Thread(target=monitor_audio, daemon=True)
monitor_thread.start()

# レベルメーターの更新開始
root.after(50, update_level_meter)

root.mainloop()
