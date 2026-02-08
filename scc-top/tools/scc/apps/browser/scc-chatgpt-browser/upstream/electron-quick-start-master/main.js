const electron = require('electron')
// 控制应用生命周期模块
const app = electron.app
// 创建原生浏览器窗口模块
const BrowserWindow = electron.BrowserWindow

const path = require('path')
const url = require('url')

// 将窗口对象设置为全局对象
// 不然的话 窗口将在对象被垃圾回收时自动关闭
let mainWindow

function createWindow () {
  // 创建浏览器窗口
  mainWindow = new BrowserWindow({width: 800, height: 600})

  // 装载应用首页
  mainWindow.loadURL(url.format({
    pathname: path.join(__dirname, 'index.html'),
    protocol: 'file:',
    slashes: true
  }))

  // 打开开发者工具
  // mainWindow.webContents.openDevTools()

  // 当窗口关闭时触发
  mainWindow.on('closed', function () {
    // 解除窗口对象的引用
    // 如果你的应用支持多窗口的话 通常你应该将窗口们保存到数组中 并删除当前窗口相关的元素
    mainWindow = null
  })
}

// 这个方法将在 Electron 初始化结束时被调用
// 并准备好创建浏览器窗口
// 一些接口只有在该事件发生后才能被使用
app.on('ready', createWindow)

// 当所有窗口关闭时退出应用
app.on('window-all-closed', function () {
  // 在 macOS 中 一般的应用和相应的菜单栏会保持活跃 直到用户使用 Cmd+Q 或右键退出
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('activate', function () {
  // 在macOS中 当点击应用的dock图标时 没有打开的应用窗口 那么会在应用中重新创建一个窗口
  if (mainWindow === null) {
    createWindow()
  }
})

// 在这个文件中 可以写主进程相关代码。
// 你也可以将它们放到不同的文件中 并且通过require引入进来

