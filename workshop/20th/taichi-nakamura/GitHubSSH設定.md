

VSCodeを使って設定するなら、\*\*「SSHキー方式」\*\*がおすすめです。

理由は、VSCodeに内蔵されているターミナル（コマンド入力画面）を使えば、**最初の設定（鍵の作成・登録・URL変更）をすべてVSCodeの画面内で完結できる**からです。

この初期設定さえ完了すれば、それ以降はVSCodeのボタン操作（またはターミナルでの`git push`）で、**パスワードやトークンの入力が一切不要**になります。

-----

### VSCodeを使ったSSH設定の手順（簡単な方）

`~/GitHub/droneschool` のフォルダをVSCodeで開いている前提で進めます。

#### ステップ1： VSCodeでターミナルを開く

まず、VSCode内でターミナルを開きます。

  * メニューバーから: **[表示] \> [ターミナル]** を選択
  * ショートカットキー: `Ctrl` + `@` （Controlキーとアットマークキー）

画面下に `ardupilot@TrigkeyS5:~/GitHub/droneschool$` のようなターミナルが表示されます。

#### ステップ2： ターミナルでSSHキーを作成する

そのターミナルで、以下のコマンドを実行します。

1.  **キーがあるか確認**

    ```bash
    ls ~/.ssh/id_rsa.pub
    ```

      * `No such file or directory` と表示されたら、次のコマンドでキーを**新規作成**します。
      * すでにファイル名が表示されたら、キーは作成済みなのでこの手順（`ssh-keygen`）はスキップし、ステップ3に進んでください。

2.  **キーの新規作成**

    ```bash
    # メールアドレスはGitHubに登録しているものを入力します
    ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
    ```

      * `Enter file in which to save the key...` と聞かれますが、何も入力せず **Enter** キーを押します。
      * `Enter passphrase...` と2回聞かれますが、これも何も入力せず **Enter** キーを押します。（これでパスワードなしの鍵が作成されます）

#### ステップ3： ターミナルで公開鍵をコピーする

次に、GitHubに登録するための公開鍵（合鍵）の中身を表示し、コピーします。

```bash
cat ~/.ssh/id_rsa.pub
```

ターミナルに `ssh-rsa AAAA...` から始まる長い文字列が表示されます。
これを**マウスですべて選択し、右クリックなどでコピー**してください。

#### ステップ4： ブラウザでGitHubに鍵を登録する

（この作業だけブラウザで行います）

1.  GitHubの [SSHキー設定ページ](https://github.com/settings/keys) を開きます。
2.  [**New SSH key**] ボタンを押します。
3.  **Title:** `TrigkeyS5` など、どのPCの鍵かわかる名前を付けます。
4.  **Key:** ステップ3でコピーした `ssh-rsa AAAA...` の文字列を貼り付けます。
5.  [**Add SSH key**] ボタンを押します。

#### ステップ5： ターミナルでリポジトリの接続設定を変更する

最後に、VSCodeのターミナルに戻り、このリポジトリ（droneschool）がHTTPSではなくSSHを使うように設定を変更します。

```bash
git remote set-url origin git@github.com:zorosdrone/droneschool.git
```

-----

### 設定完了です！

これで、VSCodeからプッシュできるようになりました。

  * **VSCodeのボタンでプッシュ:**
    左側の「ソース管理」パネル（ブランチのアイコン）を開き、コミット後、下部にある「変更の同期」（丸い矢印アイコン）を押せば、パスワード入力なしでプッシュできます。

  * **VSCodeのターミナルでプッシュ:**
    ターミナルで `git push origin 20th_taichi-nakamura` を実行しても、何も聞かれずにプッシュが完了します。