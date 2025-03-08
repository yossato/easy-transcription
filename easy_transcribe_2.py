import tkinter as tk
from tkinter import ttk
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

# 録音したWAVファイルのパスを積むキュー（(ファイルパス, ソース) のタプル）
transcription_queue = queue.Queue()

# 表示用のTreeviewで各行の完全な文字起こし結果（改行付き）を保持する辞書
full_transcriptions = {}

# レベルメーターの設定（リニア表示）
METER_WIDTH = 300
METER_HEIGHT = 30
LEVEL_METER_MAX = 32767  # 16bitの最大値

# ----------------- マイク入力とリニアレベルメーター -----------------
def monitor_audio():
    """
    常時マイクから音声を取得し、各チャンクのリニアな最大値を current_level に更新します。
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
        current_level = audioop.max(data, 2)
        if is_recording:
            frames.append(data)

def update_level_meter():
    """
    current_level のリニアな値をもとに、Canvas上に緑色のレベルメーターを描画します。
    """
    level_ratio = min(current_level / LEVEL_METER_MAX, 1.0)
    meter_fill_width = int(METER_WIDTH * level_ratio)
    meter_canvas.delete("all")
    meter_canvas.create_rectangle(0, 0, meter_fill_width, METER_HEIGHT, fill="green")
    meter_canvas.create_rectangle(0, 0, METER_WIDTH, METER_HEIGHT, outline="black")
    root.after(50, update_level_meter)

# ----------------- 文字起こし結果表示用（Treeview） -----------------
def add_transcription_row(source, transcript):
    """
    タイムスタンプと文字起こし結果を1行としてTreeviewに追加します。
    表示用の文字列は改行をスペースに置換した1行のものとし、
    完全な文字起こし結果（改行付き）は full_transcriptions に保持します。
    新しい行は常に最上段に追加されます。
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    display_text = transcript.replace("\n", " ")
    # 新しい行を index "0" に追加して最新行を上部に配置
    item_id = tree.insert("", 0, values=(timestamp, display_text))
    full_transcriptions[item_id] = transcript

def on_tree_double_click(event):
    """
    Treeview の行をダブルクリックすると、その行の完全な文字起こし結果（改行付き）をクリップボードにコピーします。
    """
    item_id = tree.focus()
    if not item_id:
        return
    transcription = full_transcriptions.get(item_id, "")
    root.clipboard_clear()
    root.clipboard_append(transcription)
    print("文字起こし結果をクリップボードにコピーしました。")

# ----------------- 文字起こし処理 -----------------
def process_srt(srt_file, source):
    """
    whisperkit-cli により出力された SRT ファイルから不要な番号・タイムスタンプ行、タグを除去し、
    テキストを抽出して Treeview に追加します。改行はそのまま保持します。
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
        add_transcription_row(source, transcript)
    else:
        add_transcription_row(source, "SRTファイルが見つかりませんでした。")

def process_transcription(file_path, source):
    """
    指定された WAV ファイルを whisperkit-cli に渡して文字起こしを実行し、
    結果の SRT ファイルからテキストを抽出して Treeview に表示します。
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
            add_transcription_row(source, f"whisperkit-cli の実行でエラーが発生しました: {e}")
            return
        srt_file = os.path.join(temp_dir, f"{base}.srt")
        process_srt(srt_file, source)

def transcription_worker():
    """
    transcription_queue に積まれた各 WAV ファイルを順次処理するワーカースレッドです。
    処理後、一時ファイルは削除します。
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
    現在の録音データ（frames）を、一意の一時 WAV ファイルとして保存し、
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

# ----------------- 録音開始・停止（個別ボタン） -----------------
def start_recording():
    """
    録音開始ボタンの処理です。録音開始時は frames をクリアし、録音状態にし、
    録音開始ボタンを無効、停止ボタンを有効にします。
    """
    global is_recording, frames
    if not is_recording:
        frames = []
        is_recording = True
        start_button.config(state="disabled")
        stop_button.config(state="normal")

def stop_recording():
    """
    録音停止ボタンの処理です。録音状態を解除し、停止ボタンを無効、開始ボタンを有効にし、
    録音データを一時ファイルに保存してキューに追加します。
    """
    global is_recording
    if is_recording:
        is_recording = False
        start_button.config(state="normal")
        stop_button.config(state="disabled")
        queue_recording()

# ----------------- GUI の構築 -----------------
root = tk.Tk()
root.title("WhisperKit 文字起こし（録音のみ・表形式）")

# 録音操作用ボタン（個別ボタン：開始／停止）
button_frame = tk.Frame(root)
button_frame.pack(pady=10)
start_button = tk.Button(button_frame, text="録音開始", command=start_recording)
start_button.pack(side="left", padx=5)
stop_button = tk.Button(button_frame, text="録音停止", command=stop_recording, state="disabled")
stop_button.pack(side="left", padx=5)

# レベルメーター表示用キャンバス
meter_canvas = tk.Canvas(root, width=METER_WIDTH, height=METER_HEIGHT, bg="white")
meter_canvas.pack(pady=10)

# Treeview とスクロールバーを含むフレームの作成（表形式表示）
tree_frame = tk.Frame(root)
tree_frame.pack(fill="both", expand=True, padx=10, pady=10)
scrollbar = ttk.Scrollbar(tree_frame, orient="vertical")
scrollbar.pack(side="right", fill="y")
tree = ttk.Treeview(tree_frame, columns=("timestamp", "transcription"), show="headings", yscrollcommand=scrollbar.set)
tree.heading("timestamp", text="Timestamp")
tree.heading("transcription", text="Transcription")
tree.column("timestamp", width=150)
tree.column("transcription", width=500)
# 新しい行が上部に追加されるので、Treeviewは最新の結果が常に上に表示されます
tree.pack(side="left", fill="both", expand=True)
scrollbar.config(command=tree.yview)
tree.bind("<Double-1>", on_tree_double_click)

# ----------------- スレッド開始 -----------------
monitor_thread = threading.Thread(target=monitor_audio, daemon=True)
monitor_thread.start()
root.after(50, update_level_meter)
worker_thread = threading.Thread(target=transcription_worker, daemon=True)
worker_thread.start()

root.mainloop()
