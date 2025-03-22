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
import json

# WhisperKitのモデルへのパス（環境に合わせて変更してください）
MODEL = "/Users/yoshiaki/Projects/whisperkit/Models/whisperkit-coreml/openai_whisper-large-v3-v20240930_626MB"

# グローバル変数
is_recording = False     # 録音中かどうかのフラグ
frames = []              # 録音中の音声データ（録音開始後にのみ追加）
current_level = 0        # 各チャンクの最大値

# レベルメーターの最終描画値（再描画の最適化用）
last_meter_fill_width = -1

# 録音したWAVファイルのパスを積むキュー（(ファイルパス, ソース) のタプル）
transcription_queue = queue.Queue()

# 表示用のTreeviewで各行の完全な文字起こし結果（改行付き）を保持する辞書
full_transcriptions = {}

# レベルメーターの設定（リニア表示）
METER_WIDTH = 300
METER_HEIGHT = 30
LEVEL_METER_MAX = 32767  # 16bitの最大値
# NGワード設定のためのグローバル変数と関数
NG_WORDS_FILE = os.path.join(os.path.dirname(__file__), "ng_words.json")
ng_words = []

def load_ng_words():
    global ng_words
    if os.path.exists(NG_WORDS_FILE):
        with open(NG_WORDS_FILE, "r", encoding="utf-8") as f:
            try:
                ng_words = json.load(f)
            except Exception:
                ng_words = []
    else:
        ng_words = []

def save_ng_words():
    with open(NG_WORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(ng_words, f, ensure_ascii=False, indent=2)

# ----------------- マイク入力とリニアレベルメーター -----------------
def monitor_audio():
    """
    録音中のみマイクから音声を取得し、各チャンクのリニアな最大値を current_level に更新します。
    """
    global current_level, frames, is_recording
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    pa = pyaudio.PyAudio()
    stream = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                     input=True, frames_per_buffer=CHUNK)
    while is_recording:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
        except Exception:
            continue
        current_level = audioop.max(data, 2)
        frames.append(data)
    # 録音が終了したらストリームを停止・終了する
    stream.stop_stream()
    stream.close()
    pa.terminate()

def update_level_meter():
    """
    録音中は50ms、録音していないときは500ms間隔でレベルメーターを更新します。
    また、前回描画した値と同じ場合はキャンバスの再描画をスキップし、無駄な処理を削減します。
    """
    global last_meter_fill_width
    if is_recording:
        level_ratio = min(current_level / LEVEL_METER_MAX, 1.0)
        interval = 50  # 録音中は短い間隔で更新
    else:
        level_ratio = 0
        interval = 500  # 録音していない場合は更新間隔を延ばす

    meter_fill_width = int(METER_WIDTH * level_ratio)
    # 前回の描画と同じ場合は再描画をスキップ
    if meter_fill_width != last_meter_fill_width:
        meter_canvas.delete("all")
        meter_canvas.create_rectangle(0, 0, meter_fill_width, METER_HEIGHT, fill="green")
        meter_canvas.create_rectangle(0, 0, METER_WIDTH, METER_HEIGHT, outline="black")
        last_meter_fill_width = meter_fill_width

    root.after(interval, update_level_meter)

# ----------------- 文字起こし結果表示用（Treeview） -----------------
def add_transcription_row(source, transcript):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    display_text = transcript.replace("\n", " ")
    item_id = tree.insert("", 0, values=(timestamp, display_text))
    full_transcriptions[item_id] = transcript
    root.clipboard_clear()
    root.clipboard_append(transcript)
    print("最新の文字起こし結果をクリップボードにコピーしました。")

def on_tree_double_click(event):
    item_id = tree.focus()
    if not item_id:
        return
    transcription = full_transcriptions.get(item_id, "")
    root.clipboard_clear()
    root.clipboard_append(transcription)
    print("文字起こし結果をクリップボードにコピーしました。")

# ----------------- 文字起こし処理 -----------------
def process_srt(srt_file, source):
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
        # NGワードを削除（スペースに置換）
        for ng in ng_words:
            transcript = transcript.replace(ng, " ")
        add_transcription_row(source, transcript)
    else:
        add_transcription_row(source, "SRTファイルが見つかりませんでした。")

def process_transcription(file_path, source):
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
    while True:
        file_path, source = transcription_queue.get()
        try:
            process_transcription(file_path, source)
        finally:
            os.remove(file_path)
            transcription_queue.task_done()

def open_settings():
    settings_window = tk.Toplevel(root)
    settings_window.title("設定")
    settings_window.resizable(False, False)

    # NGワードを表示するListboxを作成
    listbox = tk.Listbox(settings_window, width=50, height=10)
    listbox.grid(row=0, column=0, columnspan=3, padx=10, pady=10)

    for word in ng_words:
        listbox.insert(tk.END, word)

    # 新しいNGワード入力用のEntryウィジェット
    entry = tk.Entry(settings_window, width=40)
    entry.grid(row=1, column=0, padx=10, pady=5, columnspan=2)

    def add_word():
        new_word = entry.get().strip()
        if new_word and new_word not in ng_words:
            ng_words.append(new_word)
            listbox.insert(tk.END, new_word)
            save_ng_words()
            entry.delete(0, tk.END)
   
    def delete_word():
        selected_indices = listbox.curselection()
        if selected_indices:
            for index in reversed(selected_indices):
                word = listbox.get(index)
                if word in ng_words:
                    ng_words.remove(word)
                listbox.delete(index)
            save_ng_words()
   
    add_button = tk.Button(settings_window, text="追加", command=add_word)
    add_button.grid(row=1, column=2, padx=10, pady=5)

    delete_button = tk.Button(settings_window, text="削除", command=delete_word)
    delete_button.grid(row=2, column=0, padx=10, pady=5)

    close_button = tk.Button(settings_window, text="閉じる", command=settings_window.destroy)
    close_button.grid(row=2, column=2, padx=10, pady=5)

def queue_recording():
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
    global is_recording, frames, monitor_thread
    if not is_recording:
        frames = []
        is_recording = True
        start_button.config(state="disabled")
        stop_button.config(state="normal")
        # 録音開始時にマイク監視スレッドを起動
        monitor_thread = threading.Thread(target=monitor_audio, daemon=True)
        monitor_thread.start()

def stop_recording():
    global is_recording
    if is_recording:
        is_recording = False  # monitor_audioのループ条件を外す
        start_button.config(state="normal")
        stop_button.config(state="disabled")
        queue_recording()

# ----------------- GUI の構築 -----------------
root = tk.Tk()
root.title("WhisperKit 文字起こし")

top_frame = tk.Frame(root)
top_frame.pack(fill="x", padx=10, pady=10)
# Configure three columns: left spacer, center for record buttons, right for settings button
top_frame.columnconfigure(0, weight=1)
top_frame.columnconfigure(1, weight=0)
top_frame.columnconfigure(2, weight=1)

record_frame = tk.Frame(top_frame)
record_frame.grid(row=0, column=1)

start_button = tk.Button(record_frame, text="録音開始", command=start_recording)
start_button.pack(side="left", padx=5)
stop_button = tk.Button(record_frame, text="録音停止", command=stop_recording, state="disabled")
stop_button.pack(side="left", padx=5)

settings_button = tk.Button(top_frame, text="⚙", command=open_settings)
settings_button.grid(row=0, column=2, sticky="e")

meter_canvas = tk.Canvas(root, width=METER_WIDTH, height=METER_HEIGHT, bg="white")
meter_canvas.pack(pady=10)

tree_frame = tk.Frame(root)
tree_frame.pack(fill="both", expand=True, padx=10, pady=10)
scrollbar = ttk.Scrollbar(tree_frame, orient="vertical")
scrollbar.pack(side="right", fill="y")
tree = ttk.Treeview(tree_frame, columns=("timestamp", "transcription"), show="headings", yscrollcommand=scrollbar.set)
tree.heading("timestamp", text="Timestamp")
tree.heading("transcription", text="Transcription")
tree.column("timestamp", width=150)
tree.column("transcription", width=500)
tree.pack(side="left", fill="both", expand=True)
scrollbar.config(command=tree.yview)
tree.bind("<Double-1>", on_tree_double_click)

threading.Thread(target=transcription_worker, daemon=True).start()
root.after(50, update_level_meter)
load_ng_words()
root.mainloop()
