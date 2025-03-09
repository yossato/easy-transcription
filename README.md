# WhisperKit 文字起こしGUI

このアプリは、マイクからの音声録音を行い、[WhisperKit](https://github.com/argmaxinc/WhisperKit) を利用して文字起こしを実施する Python ベースの GUI アプリケーションです。  
<img width="797" alt="image" src="https://github.com/user-attachments/assets/111557bb-8a97-41c7-aaa6-c95d615e2739" />


録音した音声は一時的に WAV ファイルとして保存され、バックグラウンドで文字起こしが実行されます。  
文字起こし結果は、最新のものが上部に表示される表形式（Treeview）で確認でき、最新の結果は自動的にクリップボードにコピーされます。  
また、各結果行をダブルクリックすることで、改行を含む完全な文字起こし結果をクリップボードにコピーすることも可能です。

## 特徴

- **録音機能**  
  - マイクからの音声を録音し、WAV ファイルに一時保存  
  - 録音開始と停止を個別のボタンで操作  
  - リニアなスケールでマイク入力レベルをリアルタイムに表示  

- **文字起こし機能**  
  - [WhisperKit](https://github.com/argmaxinc/WhisperKit) のCLIを利用して音声の文字起こしを実施  
  - 文字起こし結果は自動的にテーブルの最上段に追加され、最新の結果が常に上に表示  
  - 最新の結果は自動的にクリップボードにコピーされる  
  - 表示は改行を除いた1行表示となり、ダブルクリックすると改行付きの完全な結果がクリップボードにコピーされる

- **GUI インターフェース**  
  - Tkinter を用いたシンプルかつ直感的なユーザーインターフェース  
  - 表形式 (Treeview) による結果一覧表示（スクロールバー付き）  
  - 最新の結果が上部に表示されるため、常に最新情報を確認可能

## 動作環境とインストール方法

### macOS 環境での注意点

- **Tkinter の動作について**  
  動作確認した環境M3 MacBook Air（macOS 15.3.1）では、システム標準のPythonに付属するTkinterが正常に動作しない場合がありました。  
  そのため、以下のように Homebrew を利用して環境を整えました。

- **推奨環境の構築手順**

  1. **Homebrew のインストール**  
    [公式サイトの手順](https://brew.sh)に従い、Homebrew をインストールしてください。
     ```bash
     /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
     ```

  2. **Python 3.13 のインストール**  
     ```bash
     brew install python@3.13
     ```
     ※システムのPythonではなく、Homebrew版のPythonを利用します。

  3. **TCL/TK のインストール**  
     Tkinterを正しく動作させるため、以下もインストールします。
     ```bash
     brew install tcl-tk
     brew install python-tk
     ```
     Homebrew版でpythonとtcl-tk周りを統一することが重要なようです。  

  4. **仮想環境 (venv) の作成**  
     プロジェクトディレクトリで仮想環境を作成し、アクティベートします。
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
  5. **必要なライブラリのインストール**  
     仮想環境内で、必要なライブラリをpipでインストールしてください。
     ```bash
     pip install -r requirements.txt
     ```

  6. **WhisperKit CLI のインストール**  
     [WhisperKit CLI は Homebrew 経由でインストール可能](https://github.com/argmaxinc/WhisperKit?tab=readme-ov-file#homebrew)です。  
     以下のコマンドでインストールし、システム全体から呼び出せるようにします。
     ```bash
     brew install whisperkit-cli
     ```

     せっかくHomebrewでWhisperKitをダウンロードするのですが、事前にソースコードもダウンロードしてきて[whisperKitのディレクトリに移動して、makeコマンドでモデルをダウンロードしておく必要があります](https://github.com/argmaxinc/WhisperKit?tab=readme-ov-file#swift-cli)。
     ```bash
     make setup
     make download-model MODEL=large-v3 
     ```
     ダウンロードできたらeasy-transcription.pyの MODEL にパスを設定してください。  

## 使い方

1. 起動します。

   ```bash
   python3 easy-transcription.py
   ```


1. アプリ起動後、**録音開始** ボタンをクリックして録音を開始します。  
   録音中はレベルメーターにマイク入力の音量がリニアなスケールで表示されます。

2. 録音を停止するには **録音停止** ボタンをクリックします。  
   録音停止後、音声が一時ファイルに保存され、バックグラウンドで文字起こしが開始されます。  
   完了すると、最新の文字起こし結果が表の最上段に追加され、自動的にクリップボードにコピーされます。

3. 表中の任意の行をダブルクリックすると、その行の改行を含む完全な文字起こし結果がクリップボードにコピーされます。

## ライセンス

このプロジェクトは [BSD 2-Clause](LICENSE) の下で公開されています。

