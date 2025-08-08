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

