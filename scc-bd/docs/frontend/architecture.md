# SCC 前端架构文档

## 1. 技术栈概览

### 核心技术
- **前端框架**: 原生 HTML/CSS/JavaScript (ES6+)
- **构建工具**: 可选 Webpack/Vite (如需要)
- **包管理**: npm/yarn
- **代码规范**: ESLint + Prettier

### 浏览器支持
- Chrome/Edge (最新2个版本)
- Firefox (最新2个版本)
- Safari (最新2个版本)

## 2. 项目结构

```
sccdev/
├── assets/                 # 静态资源
│   ├── css/               # 样式文件
│   │   ├── base.css       # 基础样式
│   │   ├── components.css # 组件样式
│   │   └── themes.css     # 主题配置
│   ├── js/                # JavaScript 文件
│   │   ├── main.js        # 入口文件
│   │   ├── utils/         # 工具函数
│   │   ├── modules/       # 功能模块
│   │   └── services/      # API 服务
│   ├── images/            # 图片资源
│   └── fonts/             # 字体文件
├── components/            # 可复用组件
│   ├── modal/
│   ├── table/
│   ├── form/
│   └── button/
├── pages/                 # 页面模板
├── docs/                  # 文档
│   └── frontend/
│       └── architecture.md
├── index.html            # 首页
├── package.json          # 项目配置
└── README.md
```

## 3. 架构模式

### 3.1 模块化架构
采用 ES6 模块化设计，按功能划分模块：

```javascript
// 模块结构示例
// js/modules/user.js
export class UserModule {
  constructor() {
    this.state = {};
    this.init();
  }
  
  init() {
    // 初始化逻辑
  }
  
  // 模块方法
}
```

### 3.2 组件化设计
将 UI 拆分为独立、可复用的组件：

- **基础组件**: Button, Input, Modal
- **业务组件**: DataTable, SearchForm, Chart
- **布局组件**: Header, Sidebar, Footer

## 4. 状态管理

### 4.1 轻量级状态管理
使用原生 JavaScript 实现简单状态管理：

```javascript
// js/utils/store.js
class Store {
  constructor(initialState = {}) {
    this.state = initialState;
    this.listeners = [];
  }
  
  getState() {
    return this.state;
  }
  
  setState(newState) {
    this.state = { ...this.state, ...newState };
    this.notify();
  }
  
  subscribe(listener) {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener);
    };
  }
  
  notify() {
    this.listeners.forEach(listener => listener(this.state));
  }
}

// 全局状态实例
export const globalStore = new Store({
  user: null,
  theme: 'light',
  language: 'zh-CN'
});
```

### 4.2 本地存储管理
```javascript
// js/utils/storage.js
export const storage = {
  set(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  },
  
  get(key) {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : null;
  },
  
  remove(key) {
    localStorage.removeItem(key);
  }
};
```

## 5. API 集成

### 5.1 HTTP 客户端封装
```javascript
// js/services/http.js
class HttpClient {
  constructor(baseURL = '') {
    this.baseURL = baseURL;
  }
  
  async request(url, options = {}) {
    const fullURL = this.baseURL + url;
    
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      ...options
    };
    
    try {
      const response = await fetch(fullURL, config);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('API Error:', error);
      throw error;
    }
  }
  
  get(url, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const fullUrl = queryString ? `${url}?${queryString}` : url;
    return this.request(fullUrl, { method: 'GET' });
  }
  
  post(url, data) {
    return this.request(url, {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }
  
  put(url, data) {
    return this.request(url, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }
  
  delete(url) {
    return this.request(url, { method: 'DELETE' });
  }
}

export const http = new HttpClient('/api');
```

### 5.2 API 服务层
```javascript
// js/services/api.js
import { http } from './http.js';

export const api = {
  // 用户相关
  user: {
    login: (credentials) => http.post('/auth/login', credentials),
    logout: () => http.post('/auth/logout'),
    getProfile: () => http.get('/user/profile'),
    updateProfile: (data) => http.put('/user/profile', data)
  },
  
  // 数据相关
  data: {
    getList: (params) => http.get('/data/list', params),
    getDetail: (id) => http.get(`/data/${id}`),
    create: (data) => http.post('/data', data),
    update: (id, data) => http.put(`/data/${id}`, data),
    delete: (id) => http.delete(`/data/${id}`)
  }
};
```

### 5.3 请求拦截器
```javascript
// js/services/interceptors.js
export const setupInterceptors = () => {
  // 请求拦截 - 添加 Token
  const originalFetch = window.fetch;
  window.fetch = async (...args) => {
    const [url, config = {}] = args;
    
    // 添加认证头
    const token = localStorage.getItem('token');
    if (token) {
      config.headers = {
        ...config.headers,
        'Authorization': `Bearer ${token}`
      };
    }
    
    // 显示加载状态
    document.body.classList.add('loading');
    
    try {
      const response = await originalFetch(url, config);
      
      // 处理认证失败
      if (response.status === 401) {
        localStorage.removeItem('token');
        window.location.href = '/login';
      }
      
      return response;
    } finally {
      document.body.classList.remove('loading');
    }
  };
};
```

## 6. 组件库

### 6.1 组件基础类
```javascript
// js/components/base.js
export class BaseComponent {
  constructor(element) {
    this.element = element;
    this.state = {};
  }
  
  mount() {
    // 挂载组件
  }
  
  unmount() {
    // 卸载组件
    this.cleanup();
  }
  
  setState(newState) {
    this.state = { ...this.state, ...newState };
    this.render();
  }
  
  render() {
    // 渲染逻辑
  }
  
  cleanup() {
    // 清理事件监听等
  }
}
```

### 6.2 模态框组件示例
```javascript
// js/components/modal/index.js
import { BaseComponent } from '../base.js';

export class Modal extends BaseComponent {
  constructor(options = {}) {
    super();
    this.options = {
      title: '',
      content: '',
      onConfirm: () => {},
      onCancel: () => {},
      ...options
    };
    this.element = this.createElement();
  }
  
  createElement() {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal-container">
        <div class="modal-header">
          <h3>${this.options.title}</h3>
          <button class="modal-close">&times;</button>
        </div>
        <div class="modal-body">
          ${this.options.content}
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" data-action="cancel">取消</button>
          <button class="btn btn-primary" data-action="confirm">确定</button>
        </div>
      </div>
    `;
    
    this.bindEvents(modal);
    return modal;
  }
  
  bindEvents(element) {
    element.addEventListener('click', (e) => {
      if (e.target === element || e.target.classList.contains('modal-close')) {
        this.close();
      }
      
      const action = e.target.dataset.action;
      if (action === 'confirm') {
        this.options.onConfirm();
        this.close();
      } else if (action === 'cancel') {
        this.options.onCancel();
        this.close();
      }
    });
  }
  
  open() {
    document.body.appendChild(this.element);
    document.body.classList.add('modal-open');
  }
  
  close() {
    this.element.remove();
    document.body.classList.remove('modal-open');
  }
}

// 使用方式
// const modal = new Modal({
//   title: '确认删除',
//   content: '确定要删除此项吗？',
//   onConfirm: () => console.log('确认')
// });
// modal.open();
```

### 6.3 数据表格组件
```javascript
// js/components/table/index.js
export class DataTable {
  constructor(element, options = {}) {
    this.element = element;
    this.options = {
      columns: [],
      data: [],
      pagination: true,
      pageSize: 10,
      ...options
    };
    this.currentPage = 1;
    this.init();
  }
  
  init() {
    this.render();
    this.bindEvents();
  }
  
  render() {
    const { columns, data } = this.options;
    
    this.element.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            ${columns.map(col => `<th>${col.title}</th>`).join('')}
          </tr>
        </thead>
        <tbody>
          ${data.map(row => `
            <tr>
              ${columns.map(col => `
                <td>${this.renderCell(row, col)}</td>
              `).join('')}
            </tr>
          `).join('')}
        </tbody>
      </table>
      ${this.options.pagination ? this.renderPagination() : ''}
    `;
  }
  
  renderCell(row, column) {
    if (column.render) {
      return column.render(row[column.key], row);
    }
    return row[column.key] || '';
  }
  
  renderPagination() {
    const totalPages = Math.ceil(this.options.data.length / this.options.pageSize);
    return `
      <div class="pagination">
        <button class="btn btn-prev" ${this.currentPage === 1 ? 'disabled' : ''}>上一页</button>
        <span class="page-info">${this.currentPage} / ${totalPages}</span>
        <button class="btn btn-next" ${this.currentPage === totalPages ? 'disabled' : ''}>下一页</button>
      </div>
    `;
  }
  
  bindEvents() {
    if (!this.options.pagination) return;
    
    this.element.addEventListener('click', (e) => {
      if (e.target.classList.contains('btn-prev')) {
        this.prevPage();
      } else if (e.target.classList.contains('btn-next')) {
        this.nextPage();
      }
    });
  }
  
  prevPage() {
    if (this.currentPage > 1) {
      this.currentPage--;
      this.render();
    }
  }
  
  nextPage() {
    const totalPages = Math.ceil(this.options.data.length / this.options.pageSize);
    if (this.currentPage < totalPages) {
      this.currentPage++;
      this.render();
    }
  }
}
```

## 7. 样式架构

### 7.1 CSS 变量系统
```css
/* assets/css/base.css */
:root {
  /* 主色调 */
  --color-primary: #1890ff;
  --color-primary-dark: #096dd9;
  --color-primary-light: #40a9ff;
  
  /* 功能色 */
  --color-success: #52c41a;
  --color-warning: #faad14;
  --color-error: #ff4d4f;
  --color-info: #1890ff;
  
  /* 中性色 */
  --color-text-primary: #262626;
  --color-text-secondary: #595959;
  --color-text-disabled: #bfbfbf;
  --color-border: #d9d9d9;
  --color-bg: #f0f2f5;
  
  /* 间距 */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
  
  /* 圆角 */
  --radius-sm: 2px;
  --radius-md: 4px;
  --radius-lg: 8px;
  
  /* 阴影 */
  --shadow-sm: 0 2px 4px rgba(0,0,0,0.1);
  --shadow-md: 0 4px 8px rgba(0,0,0,0.1);
  --shadow-lg: 0 8px 16px rgba(0,0,0,0.1);
}
```

### 7.2 BEM 命名规范
```css
/* Block - 块 */
.btn {}

/* Element - 元素 */
.btn__icon {}
.btn__text {}

/* Modifier - 修饰符 */
.btn--primary {}
.btn--large {}
.btn--disabled {}
```

## 8. 开发规范

### 8.1 代码组织原则
- 单一职责: 每个模块/组件只负责一个功能
- 依赖注入: 减少硬编码依赖
- 开闭原则: 对扩展开放,对修改关闭

### 8.2 文件命名规范
- 组件: `PascalCase.js` (如: `Modal.js`)
- 工具函数: `camelCase.js` (如: `dateUtils.js`)
- 样式: `kebab-case.css` (如: `data-table.css`)
- 常量: `UPPER_SNAKE_CASE`

### 8.3 注释规范
```javascript
/**
 * 函数描述
 * @param {string} param1 - 参数1说明
 * @param {number} param2 - 参数2说明
 * @returns {boolean} 返回值说明
 */
function example(param1, param2) {
  return true;
}
```

## 9. 性能优化

### 9.1 加载优化
- 代码分割与懒加载
- 图片懒加载
- CSS 关键路径优化

### 9.2 运行时优化
- 事件委托
- DOM 操作优化
- 防抖与节流

```javascript
// 防抖
export const debounce = (fn, delay) => {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
};

// 节流
export const throttle = (fn, limit) => {
  let inThrottle;
  return (...args) => {
    if (!inThrottle) {
      fn.apply(this, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
};
```

## 10. 安全规范

- XSS 防护: 输入过滤,输出转义
- CSRF 防护: Token 验证
- 敏感信息: 不在前端存储密码等敏感数据
- HTTPS: 所有 API 请求使用 HTTPS

## 11. 部署流程

1. **开发环境**
   - 本地启动开发服务器
   - 热重载实时预览

2. **构建优化**
   ```bash
   npm run build
   ```

3. **生产部署**
   - 静态资源上传 CDN
   - HTML 文件部署到服务器
   - 配置缓存策略

## 12. 目录创建命令

```bash
# 创建项目目录结构
mkdir -p sccdev/{assets/{css,js/{utils,modules,services},images,fonts},components/{modal,table,form,button},pages,docs/frontend}

# 创建基础文件
touch sccdev/index.html
touch sccdev/package.json
touch sccdev/README.md
touch sccdev/docs/frontend/architecture.md
```
