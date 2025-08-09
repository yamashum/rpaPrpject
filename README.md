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
受け取れるようになりました。例えば VPN に接続している場合のみ
ジョブを実行したいときは以下のように指定します。

```python
from workflow.scheduler import CronScheduler

def is_vpn_connected():
    # 実際のチェックは環境に合わせて実装
    return True

s = CronScheduler()
s.add_job("0 * * * * *", job, "job.lock", conditions=[is_vpn_connected])
```

条件関数が `False` を返した場合、そのジョブはスキップされます。

