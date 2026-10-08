# Local Media Library

Windows PC に保存済みの漫画・画像・動画を、完全ローカルで整理・閲覧するためのアプリです。

- ダウンロード、ブラウザー拡張、外部API、ログイン、テレメトリはありません。
- 原本の削除・移動・改名・上書きは行いません。
- 画面は `漫画`、`画像`、`動画`、`設定` に分かれています。
- 画像と動画が同じ保存フォルダに混在していても、Scannerが判定して別々のLibraryへ表示します。
- 漫画・画像・動画は別Repositoryとして扱い、Reader・Viewer・Playerも分離します。
- LAN / iPhone は Phase 2 であり、この Windows Phase 1 には含みません。

## 開発実行

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python -m local_media_library
```

データベースと再生成可能なサムネイルは、アプリの `data/` 以下に保存されます。開発実行時はリポジトリ直下、配布版はEXEの隣です。メディア原本とは分離されます。

## フォルダ判定

登録時に `漫画フォルダ` または `画像・動画フォルダ` を選びます。

- 漫画フォルダでは、画像の入った各ディレクトリを1作品として扱います。
- 画像・動画フォルダでは、混在した画像と動画を検出し、アプリ上の別々のLibraryに分類します。
- 原本を移動して整理する必要はありません。Scannerが形式を判定し、ViewerまたはPlayerを開きます。

詳細は [Stage 0監査](docs/stage-0-audit.md) と [アーキテクチャ](docs/architecture.md) を参照してください。
