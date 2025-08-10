# rpaPrpject

このリポジトリの開発環境を構築する手順を以下に記します。

## 環境構築

1. **Python 3.12 以上**と **Node.js (npm)** をインストールします。
2. Python の仮想環境を作成して有効化します。
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. 必要な Python パッケージをインストールします。
   ```bash
   pip install PyQt6
   ```
4. Node.js の依存関係をインストールします。
   ```bash
   npm install
   ```

## アプリケーションの起動

環境構築後、以下のコマンドでアプリケーションを実行できます。

```bash
python rpa_main_ui.py
```

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

