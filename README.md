# Google Drive CLI

Google Driveのファイルやフォルダをコマンドラインからダウンロードするツール
できる限りaws cliでs3を操作する感じに寄せたいと思っている。

## インストール方法

### バイナリー版（推奨）

[Releases](https://github.com/mizuamedesu/GoogleDriveCLI/releases)から最新版をダウンロード：

```bash
# Linux
wget https://github.com/mizuamedesu/GoogleDriveCLI/releases/latest/download/GD
chmod +x GD

# Windows
# GD.exe をダウンロードしてPATHの通った場所に配置
```

### Python版

#### 依存関係のインストール
```bash
pip install google-api-python-client google-auth
```

## セットアップ

### クレデンシャルの設定

サービスアカウント作成（GCPのアカウントが必要です）

Google Cloud Console → プロジェクト選択
「IAMと管理」 → 「サービスアカウント」→「サービスアカウントを作成」→ 色々入力し後、「完了」をクリック

作成されたサービスアカウントの
「操作」 → 「鍵を管理」 → 「キーを追加」→「新しい鍵を作成」
→ キーのタイプで 「JSON」選択 → ダウンロードされます

JSONファイルダウンロード → service-account.json にリネーム

#### バイナリー版
```bash
# Linux
./GD configure

# Windows
GD.exe configure
```

#### Python版
```bash
python gdrive_download.py configure
```

- サービスアカウントのJSONファイルのパスを入力
- デフォルト(未入力時)はスクリプトのある位置から見て`./service-account.json`

## 使い方

まずGoogleDriveの設定で、共有→リンクを知っている人全員にする必要があります。

### フォルダの内容を確認

#### バイナリー版
```bash
# Linux
./GD ls 1aB2cD3eF4gH5iJ6kL7mN8oP9qR0sT1uV
./GD ls "https://drive.google.com/drive/folders/1aB2cD3eF4gH5iJ6kL7mN8oP9qR0sT1uV"

# Windows
GD.exe ls 1aB2cD3eF4gH5iJ6kL7mN8oP9qR0sT1uV
GD.exe ls "https://drive.google.com/drive/folders/1aB2cD3eF4gH5iJ6kL7mN8oP9qR0sT1uV"
```

#### Python版
```bash
python gdrive_download.py ls 1aB2cD3eF4gH5iJ6kL7mN8oP9qR0sT1uV
python gdrive_download.py ls "https://drive.google.com/drive/folders/1aB2cD3eF4gH5iJ6kL7mN8oP9qR0sT1uV"
```

### ファイル・フォルダのダウンロード

#### 単一ファイル

**バイナリー版:**
```bash
# Linux
./GD cp <ファイルID> ./downloads/

# Windows
GD.exe cp <ファイルID> ./downloads/
```

**Python版:**
```bash
python gdrive_download.py cp <ファイルID> ./downloads/
```

#### フォルダ（非再帰）

**バイナリー版:**
```bash
# Linux
./GD cp <フォルダID> ./downloads/

# Windows
GD.exe cp <フォルダID> ./downloads/
```

**Python版:**
```bash
python gdrive_download.py cp <フォルダID> ./downloads/
```

#### フォルダ（再帰的）

**バイナリー版:**
```bash
# Linux
./GD cp <フォルダID> ./downloads/ --recursive
./GD cp <フォルダID> ./downloads/ -r

# Windows
GD.exe cp <フォルダID> ./downloads/ --recursive
GD.exe cp <フォルダID> ./downloads/ -r
```

**Python版:**
```bash
python gdrive_download.py cp <フォルダID> ./downloads/ --recursive
python gdrive_download.py cp <フォルダID> ./downloads/ -r
```

--recursiveのエイリアスに-rを設定してあります。

#### URLからダウンロード

**バイナリー版:**
```bash
# Linux
./GD cp "https://drive.google.com/drive/folders/1aB2cD3eF4gH5iJ6kL7mN8oP9qR0sT1uV" ./downloads/ --recursive

# Windows
GD.exe cp "https://drive.google.com/drive/folders/1aB2cD3eF4gH5iJ6kL7mN8oP9qR0sT1uV" ./downloads/ --recursive
```

**Python版:**
```bash
python gdrive_download.py cp "https://drive.google.com/drive/folders/1aB2cD3eF4gH5iJ6kL7mN8oP9qR0sT1uV" ./downloads/ --recursive
```

## 対応フォーマット

- Google Docs → `.docx`
- Google Sheets → `.xlsx`  
- Google Slides → `.pptx`
- その他のファイル → 元のフォーマットのまま

## その他

- サービスアカウントに対象フォルダの読み取り権限が必要
- 既存ファイルは上書きされます
- ショートカットファイルも自動で解決してダウンロードします