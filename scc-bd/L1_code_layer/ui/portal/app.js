/**
 * SCC 统一入口 - 应用逻辑
 * 集成所有项目的前后端
 */

const CONFIG = {
  refreshInterval: 5000,
  categories: {
    core: { name: "核心项目", icon: "⭐", color: "#ffd700" },
    service: { name: "服务组件", icon: "⚙️", color: "#58a6ff" },
    frontend: { name: "前端界面", icon: "🎨", color: "#a371f7" },
    external: { name: "外部项目", icon: "📦", color: "#8b949e" }
  }
};

let state = {
  currentView: 'dashboard',
  projects: [],
  services: [],
  lastUpdate: null,
  uptime: 0
};

async function init() {
  setupNavigation();
  setupEventListeners();
  await loadSystemStatus();
  await loadProjectsByCategory();
  startAutoRefresh();
}

function setupNavigation() {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const view = btn.dataset.view;
      switchView(view);
    });
  });

  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      filterProjects(btn.dataset.filter);
    });
  });
}

function setupEventListeners() {
  document.getElementById('projectModal').addEventListener('click', (e) => {
    if (e.target.id === 'projectModal') closeModal();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });
}

function switchView(viewName) {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === viewName);
  });
  document.querySelectorAll('.view').forEach(view => {
    view.classList.remove('active');
  });
  document.getElementById(`view-${viewName}`).classList.add('active');
  state.currentView = viewName;
  
  // 根据视图加载数据
  if (viewName === 'projects') {
    loadProjectsByCategory();
  } else if (viewName === 'services') {
    loadServicesTable();
  }
}

async function loadSystemStatus() {
  const statusGrid = document.getElementById('systemStatusGrid');
  const activeCountEl = document.getElementById('activeServicesCount');
  
  try {
    const response = await fetch('/api/portal/status?t=' + Date.now());
    const data = await response.json();
    
    if (!data.ok) {
      statusGrid.innerHTML = '<div class="status-item error">加载失败</div>';
      return;
    }
    
    statusGrid.innerHTML = '';
    const services = data.services || [];
    const online = services.filter(s => s.status === 'online').length;
    
    activeCountEl.textContent = `${online}/${services.length}`;
    
    services.forEach(service => {
      const statusItem = document.createElement('div');
      statusItem.className = 'status-item';
      statusItem.innerHTML = `
        <span class="status-indicator ${service.status}"></span>
        <span>${service.name}</span>
      `;
      statusGrid.appendChild(statusItem);
    });
    
    const systemStatus = document.getElementById('systemStatus');
    const allOnline = online === services.filter(s => s.status !== 'skipped').length;
    systemStatus.className = 'status-dot ' + (allOnline ? '' : 'warning');
    
  } catch (e) {
    statusGrid.innerHTML = '<div class="status-item error">连接失败</div>';
    console.error('Failed to load system status:', e);
  }
  
  state.lastUpdate = new Date();
  document.getElementById('lastUpdate').textContent = 
    state.lastUpdate.toLocaleTimeString('zh-CN');
}

async function loadProjectsByCategory() {
  const projectList = document.getElementById('projectList');
  const projectsGrid = document.getElementById('projectsGrid');
  
  projectList.innerHTML = '<div class="project-item loading">加载中...</div>';
  projectsGrid.innerHTML = '';
  
  try {
    const response = await fetch('/api/portal/projects/by-category?t=' + Date.now());
    const data = await response.json();
    
    if (!data.ok) {
      projectList.innerHTML = '<div class="project-item error">加载失败</div>';
      return;
    }
    
    const projects = [];
    for (const [category, items] of Object.entries(data.projects)) {
      items.forEach(item => {
        projects.push({ ...item, category });
      });
    }
    
    state.projects = projects;
    
    // 更新概览列表
    projectList.innerHTML = '';
    projects.slice(0, 5).forEach(project => {
      const projectItem = createProjectListItem(project);
      projectList.appendChild(projectItem);
    });
    
    // 更新项目网格
    projectsGrid.innerHTML = '';
    for (const [category, items] of Object.entries(data.projects)) {
      if (items.length === 0) continue;
      
      const categoryHeader = document.createElement('div');
      categoryHeader.className = 'category-header';
      categoryHeader.innerHTML = `
        <h3>${CONFIG.categories[category]?.icon || '📁'} ${CONFIG.categories[category]?.name || category}</h3>
        <span class="badge">${items.length}</span>
      `;
      projectsGrid.appendChild(categoryHeader);
      
      const categoryGrid = document.createElement('div');
      categoryGrid.className = 'category-grid';
      
      items.forEach(project => {
        const projectCard = createProjectCard(project, category);
        categoryGrid.appendChild(projectCard);
      });
      
      projectsGrid.appendChild(categoryGrid);
    }
    
  } catch (e) {
    console.error('Failed to load projects:', e);
    projectList.innerHTML = '<div class="project-item error">加载失败</div>';
  }
}

function createProjectListItem(project) {
  const item = document.createElement('div');
  item.className = 'project-item';
  item.innerHTML = `
    <div class="project-info">
      <div class="project-icon">${project.icon || '📁'}</div>
      <div class="project-meta">
        <div class="project-name">${project.name}</div>
        <div class="project-desc">${project.description || ''}</div>
      </div>
    </div>
    <div class="project-status">
      <span class="status-indicator ${project.exists ? 'online' : 'offline'}"></span>
      <span class="badge">${project.type}</span>
    </div>
  `;
  item.onclick = () => showProjectDetail(project.id);
  return item;
}

function createProjectCard(project, category) {
  const card = document.createElement('div');
  card.className = 'project-card';
  card.dataset.category = category;
  card.dataset.type = project.type;
  
  const categoryInfo = CONFIG.categories[category] || {};
  
  card.innerHTML = `
    <div class="project-card-header">
      <div class="project-card-title">${project.icon || '📁'} ${project.name}</div>
      <div class="project-card-type" style="border-color: ${categoryInfo.color || '#666'}">${categoryInfo.name || category}</div>
    </div>
    <div class="project-card-desc">${project.description || '暂无描述'}</div>
    <div class="project-card-footer">
      <span>${project.type}</span>
      <span class="status-indicator ${project.exists ? 'online' : 'offline'}"></span>
    </div>
  `;
  card.onclick = () => showProjectDetail(project.id);
  return card;
}

async function loadServicesTable() {
  const tbody = document.getElementById('servicesTableBody');
  tbody.innerHTML = '<tr><td colspan="5" class="loading">加载中...</td></tr>';
  
  try {
    const [portsRes, statusRes] = await Promise.all([
      fetch('/api/portal/ports'),
      fetch('/api/portal/status')
    ]);
    
    const portsData = await portsRes.json();
    const statusData = await statusRes.json();
    
    if (!portsData.ok) {
      tbody.innerHTML = '<tr><td colspan="5">加载失败</td></tr>';
      return;
    }
    
    const statusMap = {};
    if (statusData.ok && statusData.services) {
      statusData.services.forEach(s => {
        statusMap[s.id] = s.status;
      });
    }
    
    tbody.innerHTML = '';
    
    for (const [name, port] of Object.entries(portsData.ports)) {
      const project = state.projects.find(p => p.id === name);
      const status = statusMap[name] || 'unknown';
      
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>${name}</td>
        <td>${project?.type || 'service'}</td>
        <td><span class="status-badge ${status}">${status}</span></td>
        <td><code>http://127.0.0.1:${port}</code></td>
        <td>
          <button class="btn btn-sm" onclick="checkService('${name}')">检查</button>
          ${project ? `<button class="btn btn-sm btn-secondary" onclick="showProjectDetail('${name}')">详情</button>` : ''}
        </td>
      `;
      tbody.appendChild(row);
    }
    
  } catch (e) {
    console.error('Failed to load services:', e);
    tbody.innerHTML = '<tr><td colspan="5">加载失败</td></tr>';
  }
}

function filterProjects(filter) {
  const cards = document.querySelectorAll('.project-card');
  cards.forEach(card => {
    const category = card.dataset.category;
    const type = card.dataset.type;
    let show = false;
    
    if (filter === 'all') show = true;
    else if (filter === 'active') show = card.querySelector('.status-indicator').classList.contains('online');
    else if (filter === 'stopped') show = card.querySelector('.status-indicator').classList.contains('offline');
    else if (filter === category) show = true;
    
    card.style.display = show ? '' : 'none';
  });
}

async function showProjectDetail(projectId) {
  const modal = document.getElementById('projectModal');
  const modalTitle = document.getElementById('modalTitle');
  const modalBody = document.getElementById('modalBody');
  
  modalTitle.textContent = '加载中...';
  modalBody.innerHTML = '<div class="loading">加载项目详情...</div>';
  modal.classList.add('active');
  
  try {
    const response = await fetch(`/api/portal/projects/${projectId}`);
    const data = await response.json();
    
    if (!data.ok) {
      modalTitle.textContent = '错误';
      modalBody.innerHTML = `<div class="error">${data.error}</div>`;
      return;
    }
    
    const p = data.project;
    const categoryInfo = CONFIG.categories[p.category] || {};
    
    modalTitle.innerHTML = `${p.icon || '📁'} ${p.name}`;
    
    modalBody.innerHTML = `
      <div class="detail-section">
        <h4>基本信息</h4>
        <table class="detail-table">
          <tr><td>项目ID</td><td><code>${p.id}</code></td></tr>
          <tr><td>分类</td><td><span class="badge" style="background: ${categoryInfo.color || '#666'}">${categoryInfo.name || p.category}</span></td></tr>
          <tr><td>类型</td><td><span class="badge">${p.type}</span></td></tr>
          <tr><td>路径</td><td><code>${p.path}</code></td></tr>
          <tr><td>状态</td><td><span class="status-badge ${p.exists ? 'online' : 'offline'}">${p.exists ? '已安装' : '未安装'}</span></td></tr>
          ${p.github ? `<tr><td>GitHub</td><td><a href="https://github.com/${p.github}" target="_blank">${p.github}</a></td></tr>` : ''}
        </table>
      </div>
      
      ${p.type === 'backend' ? `
      <div class="detail-section">
        <h4>服务信息</h4>
        <table class="detail-table">
          <tr><td>端口</td><td><code>${p.port}</code></td></tr>
          <tr><td>端点</td><td><code>${p.endpoint || 'N/A'}</code></td></tr>
          <tr><td>健康检查</td><td><code>${p.health_url || 'N/A'}</code></td></tr>
          ${p.entry ? `<tr><td>入口文件</td><td><code>${p.entry}</code></td></tr>` : ''}
        </table>
      </div>
      ` : ''}
      
      ${p.stats ? `
      <div class="detail-section">
        <h4>项目统计</h4>
        <table class="detail-table">
          <tr><td>文件数</td><td>${p.stats.files || 'N/A'}</td></tr>
          <tr><td>requirements.txt</td><td>${p.stats.has_requirements ? '✅' : '❌'}</td></tr>
          <tr><td>package.json</td><td>${p.stats.has_package_json ? '✅' : '❌'}</td></tr>
          <tr><td>Dockerfile</td><td>${p.stats.has_dockerfile ? '✅' : '❌'}</td></tr>
        </table>
      </div>
      ` : ''}
      
      <div class="detail-section">
        <h4>快速操作</h4>
        <div class="action-buttons">
          ${p.type === 'frontend' ? 
            `<a href="/${p.id}/" class="btn btn-primary" target="_blank">打开界面</a>` : 
            `<button class="btn btn-primary" onclick="openProjectBackend('${p.id}')">打开 API</button>`
          }
          ${p.type === 'backend' ? `<button class="btn" onclick="checkProjectHealth('${p.id}')">健康检查</button>` : ''}
          <button class="btn btn-secondary" onclick="viewProjectCode('${p.path}')">查看代码</button>
        </div>
      </div>
    `;
    
  } catch (e) {
    modalTitle.textContent = '错误';
    modalBody.innerHTML = `<div class="error">加载失败: ${e.message}</div>`;
  }
}

function closeModal() {
  document.getElementById('projectModal').classList.remove('active');
}

async function checkService(serviceId) {
  try {
    const response = await fetch(`/api/portal/projects/${serviceId}`);
    const data = await response.json();
    
    if (!data.ok) {
      alert(`服务 ${serviceId} 未找到`);
      return;
    }
    
    const p = data.project;
    if (!p.health_url) {
      alert(`${p.name} 没有健康检查端点`);
      return;
    }
    
    const healthRes = await fetch(p.health_url + '?t=' + Date.now());
    const healthData = await healthRes.json().catch(() => ({}));
    
    alert(`${p.name} 状态: ${healthRes.ok ? '✅ 在线' : '⚠️ 异常'}\n\n${JSON.stringify(healthData, null, 2)}`);
  } catch (e) {
    alert(`检查失败: ${e.message}`);
  }
}

async function checkProjectHealth(projectId) {
  await checkService(projectId);
}

function openProject(projectId) {
  const project = state.projects.find(p => p.id === projectId);
  if (project) {
    if (project.type === 'frontend') {
      window.open(`/${project.id}/`, '_blank');
    } else if (project.endpoint) {
      window.open(project.endpoint, '_blank');
    }
  }
}

function openProjectBackend(projectId) {
  const project = state.projects.find(p => p.id === projectId);
  if (project && project.endpoint) {
    window.open(project.endpoint, '_blank');
  }
}

function viewProjectCode(projectPath) {
  // 尝试使用 VS Code 协议打开
  const fullPath = `c:/scc/${projectPath}`;
  window.open(`vscode://file/${fullPath}`, '_blank');
}

async function refreshProjects() {
  await loadProjectsByCategory();
  const btn = document.querySelector('.card-header .btn-sm');
  if (btn) {
    const originalText = btn.textContent;
    btn.textContent = '已刷新';
    setTimeout(() => btn.textContent = originalText, 1000);
  }
}

function installNewService() {
  const modal = document.getElementById('projectModal');
  const modalTitle = document.getElementById('modalTitle');
  const modalBody = document.getElementById('modalBody');
  
  modalTitle.textContent = '安装新服务';
  modalBody.innerHTML = `
    <div class="detail-section">
      <h4>从 GitHub 安装</h4>
      <p>使用以下 API 安装新的项目:</p>
      <pre><code>POST /plugins/install
Content-Type: application/json

{
  "name": "my-project",
  "github_repo": "username/repo",
  "type": "integration",
  "branch": "main",
  "entry_point": "app.py"
}</code></pre>
    </div>
    <div class="detail-section">
      <h4>手动添加</h4>
      <p>编辑 <code>router_portal.mjs</code> 文件，在 PROJECTS_CONFIG 数组中添加新项目配置。</p>
    </div>
  `;
  modal.classList.add('active');
}

function startAutoRefresh() {
  setInterval(async () => {
    if (state.currentView === 'dashboard') {
      await loadSystemStatus();
    }
  }, CONFIG.refreshInterval);

  updateUptime();
  setInterval(updateUptime, 1000);
}

function updateUptime() {
  state.uptime++;
  const hours = Math.floor(state.uptime / 3600);
  const minutes = Math.floor((state.uptime % 3600) / 60);
  const seconds = state.uptime % 60;
  
  document.getElementById('serverUptime').textContent = 
    `运行时间: ${hours}h ${minutes}m ${seconds}s`;
}

// 全局函数暴露给 HTML
document.checkService = checkService;
document.showProjectDetail = showProjectDetail;
document.closeModal = closeModal;
document.openProject = openProject;
document.openProjectBackend = openProjectBackend;
document.viewProjectCode = viewProjectCode;
document.checkProjectHealth = checkProjectHealth;
document.refreshProjects = refreshProjects;
document.installNewService = installNewService;

document.addEventListener('DOMContentLoaded', init);
