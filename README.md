# Local Media Library

Windows PC に保存済みの漫画・画像・動画を、完全ローカルで整理・閲覧するためのアプリです。

- ダウンロード、ブラウザー拡張、外部API、ログイン、テレメトリはありません。
- 原本の削除・移動・改名・上書きは行いません。
- 画面と登録フォルダは `漫画` と `画像・動画` の2つだけです。
- 内部では漫画・画像・動画を別Repositoryとして扱い、画像Viewerと動画Playerも分離します。
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
- 画像・動画フォルダでは、混在した画像と動画を同じLibraryに一覧表示します。
- 原本を移動して整理する必要はありません。Scannerが形式を判定し、ViewerまたはPlayerを開きます。

詳細は [Stage 0監査](docs/stage-0-audit.md) と [アーキテクチャ](docs/architecture.md) を参照してください。
