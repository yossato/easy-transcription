import tkinter as tk
import subprocess
import os
import tempfile
import pathlib
import re
import threading
import pyaudio
import wave
import audioop
import queue
from datetime import datetime

# WhisperKitのモデルへのパス（環境に合わせて変更してください）
MODEL = "/Users/yoshiaki/Projects/whisperkit/Models/whisperkit-coreml/openai_whisper-large-v3-v20240930_626MB"

# グローバル変数
is_recording = False     # 録音中かどうかのフラグ
frames = []              # 録音中の音声データ（録音開始後にのみ追加）
current_level = 0        # 各チャンクの最大値

# 録音したWAVファイルのパスを積むキュー（タプル: (ファイルパス, ソース名)）
transcription_queue = queue.Queue()

# レベルメーターの設定（リニア表示）
METER_WIDTH = 300
METER_HEIGHT = 30
LEVEL_METER_MAX = 32767  # 16bitの最大値

# ----------------- マイク入力とリニアレベルメーター -----------------
def monitor_audio():
    """
    常時マイクから音声を取得し、各チャンクの最大値を current_level に更新します。
    録音中の場合は frames にも追加します。
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
        # リニアな最大値を取得
        current_level = audioop.max(data, 2)
        if is_recording:
            frames.append(data)

def update_level_meter():
    """
    current_level のリニアな値を基に、Canvas上に緑色のレベルメーターを描画します。
    """
    level_ratio = min(current_level / LEVEL_METER_MAX, 1.0)
    meter_fill_width = int(METER_WIDTH * level_ratio)
    meter_canvas.delete("all")
    meter_canvas.create_rectangle(0, 0, meter_fill_width, METER_HEIGHT, fill="green")
    meter_canvas.create_rectangle(0, 0, METER_WIDTH, METER_HEIGHT, outline="black")
    root.after(50, update_level_meter)

# ----------------- 文字起こし結果表示用セル -----------------
def add_transcription_cell(source, transcript):
    """
    タイムスタンプと文字起こし結果を持つセルを生成して表示領域に追加します。
    セル内の文字起こし結果部分をダブルクリックすると、その内容のみがクリップボードにコピーされます（タイムスタンプは除く）。
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cell_frame = tk.Frame(result_frame, bd=1, relief="solid", padx=5, pady=5)
    # タイムスタンプ（コピー対象外）
    ts_label = tk.Label(cell_frame, text=timestamp, fg="blue", font=("Arial", 10, "bold"))
    ts_label.pack(anchor="w")
    # 文字起こし結果（コピー対象）
    text_label = tk.Label(cell_frame, text=transcript, justify="left", wraplength=500)
    text_label.pack(anchor="w", pady=(2, 0))
    # ダブルクリックでコピー（タイムスタンプは含めずテキストのみ）
    text_label.bind("<Double-Button-1>", lambda e, t=transcript: copy_to_clipboard(t))
    cell_frame.pack(fill="x", pady=2, padx=2)
    result_canvas.update_idletasks()
    result_canvas.config(scrollregion=result_canvas.bbox("all"))

def copy_to_clipboard(text):
    """
    指定されたテキストをクリップボードへコピーします。
    ※改行コードは"\n"のままとなり、Macの他のテキストエディタでもそのまま貼り付けられます。
    """
    root.clipboard_clear()
    root.clipboard_append(text)
    print("文字起こし結果をクリップボードにコピーしました。")

# ----------------- 文字起こし処理 -----------------
def process_srt(srt_file, source):
    """
    whisperkit-cli により出力されたSRTファイルから不要な番号・タイムスタンプ行、タグを除去し、
    テキストを抽出して表示用セルに追加します。
    改行コードはそのまま"\n"として保持します。
    """
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
        add_transcription_cell(source, transcript)
    else:
        add_transcription_cell(source, "SRTファイルが見つかりませんでした。")

def process_transcription(file_path, source):
    """
    指定されたWAVファイルをwhisperkit-cliに渡して文字起こしを実行し、
    結果のSRTファイルからテキストを抽出して表示します。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        base = os.path.splitext(os.path.basename(file_path))[0]
        whisperkit_cmd = [
            "whisperkit-cli",
            "transcribe",
            "--audio-path", file_path,
            "--model-path", MODEL,
            "--language", "ja",
            "--report",
            "--report-path", temp_dir
        ]
        try:
            subprocess.run(whisperkit_cmd, check=True)
        except subprocess.CalledProcessError as e:
            add_transcription_cell(source, f"whisperkit-cli の実行でエラーが発生しました: {e}")
            return
        srt_file = os.path.join(temp_dir, f"{base}.srt")
        process_srt(srt_file, source)

def transcription_worker():
    """
    transcription_queue に積まれた各WAVファイルを順次処理するワーカースレッドです。
    処理後は一時ファイルを削除します。
    """
    while True:
        file_path, source = transcription_queue.get()
        try:
            process_transcription(file_path, source)
        finally:
            os.remove(file_path)
            transcription_queue.task_done()

def queue_recording():
    """
    現在の録音データ（frames）を、一意の一時WAVファイルとして保存し、
    そのファイルパスとソース情報を transcription_queue に追加します。
    """
    global frames
    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp_file_name = temp_file.name
    temp_file.close()
    wf = wave.open(temp_file_name, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(2)  # 16ビット = 2バイト
    wf.setframerate(16000)
    wf.writeframes(b"".join(frames))
    wf.close()
    transcription_queue.put((temp_file_name, "録音"))

# ----------------- 録音 -----------------
def toggle_recording():
    """
    録音開始/停止のトグル処理です。録音停止時は録音データを一時ファイルに保存し、
    キューに追加してワーカーが処理するようにします。
    """
    global is_recording, frames
    if not is_recording:
        frames = []
        is_recording = True
        record_button.config(text="録音停止")
    else:
        is_recording = False
        record_button.config(text="録音開始")
        queue_recording()

# ----------------- GUI の構築 -----------------
root = tk.Tk()
root.title("WhisperKit 文字起こし（録音のみ）")

# 録音開始/停止トグルボタン
record_button = tk.Button(root, text="録音開始", command=toggle_recording)
record_button.pack(pady=10)

# レベルメーター表示用キャンバス（常時表示）
meter_canvas = tk.Canvas(root, width=METER_WIDTH, height=METER_HEIGHT, bg="white")
meter_canvas.pack(pady=10)

# 文字起こし結果をリスト形式で表示する領域（スクロール付き）
result_container = tk.Frame(root)
result_container.pack(fill="both", expand=True, padx=10, pady=10)
result_canvas = tk.Canvas(result_container)
result_scrollbar = tk.Scrollbar(result_container, orient="vertical", command=result_canvas.yview)
result_canvas.configure(yscrollcommand=result_scrollbar.set)
result_scrollbar.pack(side="right", fill="y")
result_canvas.pack(side="left", fill="both", expand=True)
result_frame = tk.Frame(result_canvas)
result_canvas.create_window((0, 0), window=result_frame, anchor="nw")

# ----------------- スレッド開始 -----------------
monitor_thread = threading.Thread(target=monitor_audio, daemon=True)
monitor_thread.start()
root.after(50, update_level_meter)
worker_thread = threading.Thread(target=transcription_worker, daemon=True)
worker_thread.start()

root.mainloop()
