# ドローンエンジニア養成塾１８期フライトコードグループワーク
## フォルダ説明
### ArduCopter：フライトコード修正対応C++プログラム格納(ardupilot/ArduCopterフォルダに格納してビルド)
1. APM_Config.h：MODE_MYFIRST_ENABLED設定追加、MODE_ALT_HOLD_SIMPLE_ENABLED設定追加、MODE_LOITER_SUPER_SIMPLE_ENABLED設定追加
2. Copter.h：ModeMyfirst/ModeAltHoldSimple/ModeLoiterSuperSimpleモード追加
3. mode.cpp：Mode *Copter::mode_from_mode_num()に追加モードポインタ返却追加
4. mode.h：enum cless Numberに追加モード値追加：99/100/101、ModeAltHoldSimple、ModeLoiterSuperSimple、ModeMyfirstクラス追加
5. Parameters.cpp：doxygen用FLTMODE1値説明に99,100,101を追加
6. mode_althold_simple.cpp：mode_althold.cppをベースに追加モード対応：init()/run()処理修正、exit()処理追加
7. mode_loiter_super_simple.cpp：mode_loiter.cppをベースに追加モード対応：init()/run()処理修正、exit()処理追加
8. mode_myfirst.cpp：ワークショップ時に追加したモード処理

### Lua：追加モードを制御するスクリプト格納
1. force-change-simple.lua : ALT_HOLD_SIMPLE/LOITER_SUPERSIMPLEモード切り替えスクリプト

## Team1（SIMPLE IS BEST）テーマ案概要（坂本案説明資料）

以下２案提案します。（グループメンバー向け）
比較的作業量が少なくて役に立つのは案１だとは思います。
特に異論がなければ案１は各自提出期限（Day4）までに対応。

操縦の腕に関係なく空撮目的なら案２です。
但し、案２はCIRCLEモードという名前で既にArduPilotでは対応済みです。
案２は解析してどのように実現しているのかを確認するのみにしたいと思います。

疑問点や解決できないような問題があれば適宜Team1チャット投稿して相談。

ちなみにドローンスクールでよく使われている機体のマニュアルも参考にしてみてください
https://dl.djicdn.com/downloads/phantom_4_pro/20211129/UM/Phantom_4_Pro_Pro_Plus_Series_User_Manual_JP.pdf

### 前提情報
講義でRC3の数値を変えて離陸させたりしていましたが、講義で説明された通り指定する値はPWM値です。中心値は概ね1500です。これはRC1（ロール：エルロン）、RC２（ピッチ：エレベータ）、RC3（スロットル）、RC４（ヨー：ラダー）の場合はスティックがスプリングで中心に戻った時の値となります。プロポのスティックにスプリングがない場合があり、その場合は自分で操作して中心位置に戻す必要があります。
また、このPWM値はON/OFFするだけのスイッチも同様になっていて０か１かではなくある程度の範囲を持った値になります。この値の範囲はプロポ側の設定で変えられます。
RC5はデフォルトではモード切り替えスイッチとして３段階に切り替わるスイッチを割り当て、工夫しなければSTABILIZE/ALT_HOLD/LOITERのように３択の操作しかできません。プロポの例としてフタバT10Jは以下です。

https://www.rc.futaba.co.jp/products/detail/I00000006


## 案１：シンプルモード対応
### 背景
DJIなどの市販ドローンの機能にはなくArduPilotにはある機能（モード）にSIMPLE/SUPERSIMPLEがあります。
https://ardupilot.org/copter/docs/simpleandsuper-simple-modes.html

ドローン機体の機首の向きに関わらず操縦士の見た目でドローンの操縦ができるモードです。
便利機能というか初心者向けの機能であるにも関わらずArduPilotの機能として「宣伝」が足りないと思います。

SIMPLEモードは本来プロポでのみ切り替え可能な機能です。但し、プロポのスイッチに割り当てられるスイッチの数には限りがあります。現実的には個別のスイッチにSIMPLE/SUPERSIMPLEをプロポ操作で切り替え可能にするのはかなりの工夫が必要です。

このモード切替対応によりスイッチを1つ割り当てるだけでSTABILIZE/ALT_HOLD/LOITER/ALT_HOLD+SIMPLE/LOITER+SUPERSIMPLEの５通りの切り替えがプロポ操作で可能となります。

### 仕様
#### モードを２つ追加する
※ワークショップとほぼ同じやり方ですが、run()の修正だけではなくinit()とexit()の対応が必要です。
init()はそのモードに切り替わった時に最初に実行される処理、exit()はそのモードから他のモードに切り替えられたときに切り替え前のモードで最後に実行される処理です。

1. ALT_HOLD_SIMPLE：100
   ※ALT_HOLDをベースにしてSIMPLEモードに設定するモード
2. LOITER_SUPERSIMPLE：101
   ※LOITERをベースにしてSUPERSIMPLEモードに設定するモード

SIMPLE/SUPERSIMPLEへの切り替えのやり方は
ArduCopter/RC_Channel.cppでset_simple_mode()を使っている部分と
AP_State.cppに記述されているset_simple_mode()処理を確認して対応します。

両方のモードに本来のモードから切り替えられてもRC（プロポ）の操作でSIMPLEモードON/OFF操作（プロポのスイッチに割り当てることができる）がされた場合にはそちらの操作を優先するようにします。
また、上記2つのモードから他のモードに切り替える際にはset_simple_mode()でOFF（NONE）に設定します。
なお、後述のLUAでの処理が成立するためにはRC5が変わったらモード切替処理を行うようになっていることが前提となります。この前提が正しければRC5の状態が変わらない状態のまま強制的にモードを切り替えても元のモードに戻らないはずです。この前提が間違っている場合はその部分の修正も必要となります。

### LUAと組み合わせる
※基本はワークショップと同じやり方です。
update()で現在のモードを監視してALT_HOLDに設定されたらALT_HOLD_SIMPLEに切り替えるようにします。
同様にLOITERに設定されたらLOITER_SUPERSIMPLEに切り替えます。
　　　　　
上記処理はRC8チャンネルに割り当てられたプロポのスイッチがONの時のみ有効化するようにします。
スイッチのON/OFF判定はRC8チャンネルのPWM値が1500未満の時OFF、1500以上の時にONとします。
RC8スイッチ状態が変わった時にもRC5が切り替わった時と同様にモード切替を行うようにする必要があります。
つまり、RC8がOFFからONに切り替わった時に元のモードを記憶しておき、RC8が再びOFFになった時には記憶していたモードに戻す処理が必要です。通常考えられるスイッチ切り替えのパターンについて検討が必要です。

### 動作確認方法
#### シミュレータ設定
Ubuntu上でSITLを起動してMPと接続して、RC5（モード切り替えスイッチ）とフライトモードの対応付けを設定します。
初期設定⇒必須ハードウェア⇒フライトモードで設定画面が出ます。
この設定で実はSIMPLEモード設定できるのですが今回はそれはやりません。
この設定どおりにRC5の値を変更するとモードが切り替わります。
RC8と機能の割り当てもRC8_OPTIONパラメータでできますが、設定はしないままで確認できると思います。

#### SIMPLE/SUPERSIMPLE確認
SITL起動してRC5の値変更（STBILIZE/ALT_HOLD/LOITER）でモード切り替え実施後,ヨーを操作して機首の向きを変えたあとでRC1（ロール）とRC2（ピッチ）を操作して仕様通りの動きかどうか確かめます。

#### モード切り替え組み合わせ確認
RC5とRC8の組み合わせで5通りの切り替え（5パターン）で仕様通りのモード切り替え動作を確認します。


## 案２：ノーズインサークルモード（こちらは課題としては未対応）
### 背景
ノーズインサークルとは、空撮時、被写体を中心に、その周りを円を描くように旋回させる方法です。
モードで切り替えられれば便利です。
ノーズインサークルの説明は以下など。
https://drone-navigator.com/drone-aerial-photography-techniques#i-2

### 操作イメージ（例）
※既にCIRCLEモードがあるので以下はあくまで参考です。
https://ardupilot.org/copter/docs/circle-mode.html#circle-mode

1. 中心にしたい位置を覚えさせるモードに切り替える
　　※切り替えた時の緯度経度を覚える
　　※覚えたら切り替える前のモードに戻す
　　※LOITERベース
2. 撮影対象(円の中心)から離れるまで飛ばして旋回させたい距離になったら
　　ノーズインサークルモードに切り替える
3. ロール操作をするとノーズインサークル飛行を行う
　　※ロール操作で自動的に中心との距離が一定になるようにヨーとピッチを可変させる
　　※計算処理が面倒だと思います。
　　※他のモードに切り替えるまでヨーとピッチ操作は無効にする

以上
