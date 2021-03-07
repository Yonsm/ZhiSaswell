# [https://github.com/Yonsm/ZhiSaswell](https://github.com/Yonsm/ZhiSaswell)

Saswell Climate Component for HomeAssistant

[Saswell](https://www.saswell.com/) 地暖温控面板插件。从官方服务器拉取数据，比官方 app 使用和操作方便多了。

## 1. 安装准备

把 `zhisaswell` 放入 `custom_components`；也支持在 [HACS](https://hacs.xyz/) 中添加自定义库的方式安装。

## 2. 配置方法

参见 [我的 Home Assistant 配置](https://github.com/Yonsm/.homeassistant) 中 [configuration.yaml](https://github.com/Yonsm/.homeassistant/blob/main/configuration.yaml)

```
climate:
  - platform: zhisaswell
    #name: Saswell
    username: ***@email.com
    password: ********
    #scan_interval: 300
```

`scan_interval` 可以自行调整状态拉取时间间隔秒数，默认五分钟同步一次温度和状态，是不是慢了点儿，不过地暖本来就很慢：）

## 3. 使用方式

![PREVIEW](https://github.com/Yonsm/ZhiSaswell/blob/main/PREVIEW.png)

目前仅验证了 SAS920WHL-7W-WIFI 型号可用（价格 368 RMB），如果其它型号需要支持请给我[提 issue](https://github.com/Yonsm/ZhiSaswell/issues)。

另外有部分房间用的是 SAS920WHL-7W 型号无 WIFI 周编程版（价格 199 RMB），每天 4-6 个时间点定期自动切换，也够用了。另外自行更换面板很容易，我原来是沃茨 W-H4111L（杭州意格供暖奸商竟然不给有周编程功能的 W-H4111P ，不然就不用这么折腾了）

## 4. 参考

-   [ZhiDash](https://github.com/Yonsm/ZhiDash)
-   [Yonsm.NET](https://yonsm.github.io/saswell)
-   [Hassbian.com](https://bbs.hassbian.com/thread-3387-1-1.html)
-   [Yonsm's .homeassistant](https://github.com/Yonsm/.homeassistant)