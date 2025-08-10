# rpaPrpject

このリポジトリの開発環境を構築する手順を以下に記します。

## 環境構築（初心者向け）

以下の手順で開発環境を準備できます。

1. **必要なソフトをインストールする**
   - [Python 3.12 以上](https://www.python.org/downloads/) をインストールします。インストール時に「Add python to PATH」にチェックを入れてください。
   - [Node.js（npm 同梱）](https://nodejs.org/ja) の LTS 版をインストールします。
   - ターミナル（またはコマンドプロンプト）で `python --version` と `node --version` を実行し、バージョンが表示されることを確認します。
2. **プロジェクトのフォルダに移動する**
   - 例: `cd rpaPrpject`
3. **Python の仮想環境を作成して有効化する**
   - Mac/Linux:
     ```bash
     python -m venv venv
     source venv/bin/activate
     ```
   - Windows:
     ```cmd
     python -m venv venv
     venv\\Scripts\\activate
     ```
4. **Python の依存パッケージをインストールする**
   ```bash
   pip install -r requirements.txt
   pip install PyQt6
   ```
5. **Node.js の依存パッケージをインストールする**
   ```bash
   npm install
   ```

## アプリケーションの起動

環境構築後、以下のコマンドでアプリケーションを実行できます。

```bash
python rpa_main_ui.py
```

## ダッシュボード

FastAPI ベースのオーケストレータ API を起動すると、ブラウザからジョブの状態や実行統計を確認できます。

```bash
uvicorn workflow.orchestrator_api:app --reload
```

起動後は [http://localhost:8000/](http://localhost:8000/) にアクセスするとジョブ一覧が表示されます。`/stats` エンドポイントでは以下の情報を確認できます。デフォルトは JSON 形式で、`?format=html` を付けると HTML でも表示できます。

- 全体の成功率と平均実行時間
- 失敗理由の集計
- セレクタの成功率
- 日/週/月ごとの集計
- フロー別集計

## ロックファイル

ワークフロー実行中は `runs/runner.lock` というファイルに排他ロックを取得し、
同時に複数のフローが動作しないようにしています。実行が終了するか `stop()`
が呼び出されるとロックは解放され、ファイルも削除されます。

## Web アクション

Playwright を利用した Web ページ操作用のアクションをサポートしています。  
利用可能なアクションの例:

- `open`
- `click`
- `fill`
- `select`
- `upload`
- `wait_for`
- `download`
- `evaluate`
- `screenshot`

## 画像検索と座標の拡張

`find_image` アクションはスケール(`scale`)、色の許容度(`tolerance`)、
DPI(`dpi`)を指定できるようになりました。これらのパラメータは画面からの
画像探索をより柔軟にします。

座標を利用する `click_xy` アクションや GUI ツールの
`capture_coordinates` は、座標の基準を `Element`、`Window`、`Screen`
から選択できる `basis` パラメータと、クリックを実行せずに座標を返す
`preview` フラグをサポートします。

## 環境チェックのフック

`CronScheduler.add_job` は環境を確認するための条件コールバックを
受け取れます。`workflow.scheduler` にはよく使うチェックとして
`is_vpn_connected`、`is_ac_powered`、`is_screen_locked` のヘルパー関数を
用意しました。例えば VPN 接続かつ AC 電源使用時のみジョブを実行する
には次のように指定します。

```python
from workflow.scheduler import (
    CronScheduler,
    is_vpn_connected,
    is_ac_powered,
)

s = CronScheduler()
s.add_job(
    "0 * * * * *",
    job,
    "job.lock",
    conditions=[is_vpn_connected, is_ac_powered],
)
```

条件関数が `False` を返した場合、そのジョブはスキップされます。

## フロー操作のロール設定

`Flow.meta.roles` に操作名をキーとしたロールを定義すると、フローごとに操作権限を設定できます。指定可能な操作には `view`・`edit`・`publish`・`approve` などがあり、対応する `Runner.view_flow()` や `Runner.edit_flow()` などのメソッド呼び出し時にチェックされます。

```json
{
  "meta": {
    "roles": {
      "view": ["viewer"],
      "edit": ["editor"],
      "publish": ["publisher"],
      "approve": ["approver"]
    }
  }
}
```

## テーブルウィザード

`table.wizard` は列ヘッダ名やインデックスから検索条件を組み立て、
内部で `table.find_row` と `row.select` を実行するアクションです。
例えば次のように記述すると `name` 列が `Alice` の行を選択できます。

```json
{
  "id": "find",
  "action": "table.wizard",
  "selector": {"mock": {}},
  "params": {"query": "name=Alice", "select": true},
  "out": "row"
}
```

上記例では検索結果の行オブジェクトが `row` 変数に格納されます。

## Action Visibility Policy

ユーザーインターフェースで非表示にするアクションは、実行エンジンからも
削除もしくは無効化する必要があります。UI とエンジン側の定義が異なると、
予期しない動作や保守性の低下につながります。使用しないアクションは
`workflow.actions` から除外し、`list_actions()` の結果にも含めないよう
にしてください。

