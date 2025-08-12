# Google Drive CLI

Google Driveのファイルやフォルダをコマンドラインからダウンロードするツール
できる限りaws cliでs3を操作する感じに寄せたいと思っている。

## セットアップ

### 依存関係のインストール
```bash
pip install google-api-python-client google-auth
```

### クレデンシャルの設定

サービスアカウント作成（GCPのアカウントが必要です）

Google Cloud Console → プロジェクト選択
「IAMと管理」 → 「サービスアカウント」→「サービスアカウントを作成」→ 色々入力し後、「完了」をクリック

作成されたサービスアカウントの
「操作」 → 「鍵を管理」 → 「キーを追加」→「新しい鍵を作成」
→ キーのタイプで 「JSON」選択 → ダウンロードされます

JSONファイルダウンロード → service-account.json にリネーム

```bash
python gdrive_download.py configure
```
- サービスアカウントのJSONファイルのパスを入力
- デフォルト(未入力時)はスクリプトのある位置から見て`./service-account.json`

## 使い方

まずGoogleDriveの設定で、共有→リンクを知っている人全員にする必要があります。

### フォルダの内容を確認
```bash
# フォルダIDで確認
python gdrive_download.py ls 1aB2cD3eF4gH5iJ6kL7mN8oP9qR0sT1uV

# URLで確認
python gdrive_download.py ls "https://drive.google.com/drive/folders/1aB2cD3eF4gH5iJ6kL7mN8oP9qR0sT1uV"
```

### ファイル・フォルダのダウンロード

#### 単一ファイル
```bash
python gdrive_download.py cp <ファイルID> ./downloads/
```

#### フォルダ（非再帰）
```bash
python gdrive_download.py cp <フォルダID> ./downloads/
```

#### フォルダ（再帰的）
```bash
python gdrive_download.py cp <フォルダID> ./downloads/ --recursive
```

```bash
python gdrive_download.py cp <フォルダID> ./downloads/ --r
```

--recursiveのエイリアスに--rを設定してあります。

#### URLからダウンロード
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