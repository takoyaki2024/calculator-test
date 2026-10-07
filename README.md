# Local Media Library

Windows PC に保存済みの漫画・画像・動画を、完全ローカルで整理・閲覧するためのアプリです。

- ダウンロード、ブラウザー拡張、外部API、ログイン、テレメトリはありません。
- 原本の削除・移動・改名・上書きは行いません。
- 漫画・画像・動画は独立した Library / Repository / Viewer として扱います。
- LAN / iPhone は Phase 2 であり、この Windows Phase 1 には含みません。

## 開発実行

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python -m local_media_library
```

データベースと再生成可能なサムネイルは、アプリの `data/` 以下に保存されます。開発実行時はリポジトリ直下、配布版はEXEの隣です。メディア原本とは分離されます。

## フォルダ判定

登録時に `自動判定 / 漫画 / 画像 / 動画` を選べます。

- 自動判定では、同一ディレクトリに2枚以上の画像があり動画がない場合、そのディレクトリを漫画1作品として扱います。
- 画像と動画が混在するディレクトリでは、画像は画像Library、動画は動画Libraryへ分離します。
- 実データ構造が明確な場合は、フォルダ種別を明示すると推測を避けられます。

詳細は [Stage 0監査](docs/stage-0-audit.md) と [アーキテクチャ](docs/architecture.md) を参照してください。
