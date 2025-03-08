import tkinter as tk
from tkinter import filedialog
import subprocess
import os
import tempfile
import pathlib
import re  # 正規表現モジュールを追加

# WhisperKitのモデルへのパスを環境に合わせて書き換えてください
MODEL = "/Users/yoshiaki/Projects/whisperkit/Models/whisperkit-coreml/openai_whisper-large-v3-v20240930_626MB"


def transcribe_audio():
    # 音声ファイルをGUIで選択
    audio_file = filedialog.askopenfilename(
        filetypes=[
            ("音声ファイル", "*.wav *.mp3 *.m4a *.flac *.aac *.ogg *.mov *.mp4"),
            ("すべてのファイル", "*.*")
        ]
    )
    if not audio_file:  # キャンセルされた場合
        return

    # ファイル名（拡張子除く）を取得
    basename = pathlib.Path(audio_file).stem

    # 一時作業ディレクトリを作成
    with tempfile.TemporaryDirectory() as temp_dir:
        # 変換後のWAVファイルパス
        wav_file = os.path.join(temp_dir, f"{basename}.wav")

        # 1. ffmpegを使って16kHz, モノラル, PCM(WAV)に変換
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

        # 2. whisperkit-cli で文字起こし
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

        # 出力されたSRTファイルを読み取り、不要な行やタグを削除して表示
        srt_file = os.path.join(temp_dir, f"{basename}.srt")
        if os.path.exists(srt_file):
            with open(srt_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            processed_lines = []
            for line in lines:
                # 改行コードを除去
                line = line.rstrip("\n")
                # 不要な番号のみの行を削除（例: "1", "2", ...）
                if re.match(r'^\d+$', line.strip()):
                    continue
                # タイムスタンプ行を削除（例: "00:00:01,000 --> 00:00:04,000"）
                if re.match(r'^\d{2}:\d{2}:\d{2},\d{3} -->', line):
                    continue
                # 各行中のタグ（<|...|> で囲まれた部分）を削除
                line = re.sub(r'<\|[^|]+\|>', '', line)
                # 空行はスキップ
                if not line.strip():
                    continue
                processed_lines.append(line)

            # 改行コードを LF -> CR に変換
            transcript = "\n".join(processed_lines)
            processed_transcript = transcript.replace("\n", "\r")
            result_label.config(text=processed_transcript)
        else:
            result_label.config(text="SRTファイルが見つかりませんでした。")


# --- GUI部分 ---
root = tk.Tk()
root.title("WhisperKit 文字起こしサンプル")

transcribe_button = tk.Button(root, text="音声ファイルを選択して文字起こし", command=transcribe_audio)
transcribe_button.pack(pady=20)

result_label = tk.Label(root, text="", justify="left", wraplength=600, bg="white", anchor="nw")
result_label.pack(padx=20, pady=20, fill="both", expand=True)

root.mainloop()
