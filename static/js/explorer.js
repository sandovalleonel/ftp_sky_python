const NON_EDITABLE_EXTENSIONS = ['.zip', '.tar', '.rar', '.gz', '.7z', '.jpeg', '.jpg', '.png', '.gif', '.exe', '.dll', '.jar', '.class', '.so', '.pdf', '.mp3', '.mp4', '.iso', '.bin', '.obj'];

class AppExplorer {
    constructor() {
        this.host = '';
        this.user = '';
        this.pass = '';
        this.currentPath = '';
        this.currentEditingFile = '';
        
        // Cargar estado de localStorage
        this.expandedFolders = new Set(JSON.parse(localStorage.getItem('ftpExpanded') || '[]'));
        
        this.initEventListeners();
        this.checkExistingLogin();
    }

    initEventListeners() {
        document.getElementById('login-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.connect();
        });

        // Drag and drop events en el main-panel
        const panel = document.getElementById('main-panel');
        panel.addEventListener('dragover', (e) => { e.preventDefault(); panel.classList.add('dragover'); });
        panel.addEventListener('dragleave', (e) => { e.preventDefault(); panel.classList.remove('dragover'); });
        panel.addEventListener('drop', (e) => {
            e.preventDefault();
            panel.classList.remove('dragover');
            if(this.currentPath) {
                this.handleDropFiles(e.dataTransfer.files);
            } else {
                this.showToast('Selecciona una carpeta destino primero', 'error');
            }
        });
    }

    // --- State Management ---
    saveExpandedState() {
        localStorage.setItem('ftpExpanded', JSON.stringify([...this.expandedFolders]));
    }

    checkExistingLogin() {
        const h = sessionStorage.getItem('ftpHost');
        const u = sessionStorage.getItem('ftpUser');
        if(h && u) {
            this.host = h; this.user = u; this.pass = sessionStorage.getItem('ftpPass') || '';
            document.getElementById('login-modal').classList.add('hidden');
            this.loadInitialDisks();
        }
    }

    async doApiCall(endpoint, payload = null, method = 'POST') {
        const headers = {
            'X-FTP-Host': this.host,
            'X-FTP-User': this.user,
            'X-FTP-Pass': this.pass,
            'Content-Type': 'application/json'
        };
        const options = { method, headers };
        if (payload && !(payload instanceof FormData)) {
            options.body = JSON.stringify(payload);
        } else if (payload instanceof FormData) {
            delete headers['Content-Type']; // Let browser set boundary
            options.body = payload;
        }

        try {
            const res = await fetch(`/api/${endpoint}`, options);
            const data = await res.json();
            if(data.status === 'error') throw new Error(data.message);
            return data;
        } catch (e) {
            this.showToast(e.message, 'error');
            throw e;
        }
    }

    // --- Connection & Tree ---
    async connect() {
        const btn = document.querySelector('#login-form button');
        btn.innerHTML = '<span class="loader"></span> Conectando...';
        btn.disabled = true;

        this.host = document.getElementById('ftp-host').value;
        this.user = document.getElementById('ftp-user').value;
        this.pass = document.getElementById('ftp-pass').value;

        try {
            const data = await this.doApiCall('connect', {host: this.host, user: this.user, password: this.pass});
            sessionStorage.setItem('ftpHost', this.host);
            sessionStorage.setItem('ftpUser', this.user);
            sessionStorage.setItem('ftpPass', this.pass);
            
            document.getElementById('connection-status').innerText = `Conectado a ${this.user}@${this.host}`;
            document.getElementById('login-modal').classList.add('hidden');
            
            this.renderTreeRoot(data.disks);
            this.showToast('Conexión exitosa', 'success');
        } catch(e) {
            // Toast already shown in doApiCall
        } finally {
            btn.innerText = 'Conectar';
            btn.disabled = false;
        }
    }

    async loadInitialDisks() {
        try {
            const data = await this.doApiCall('connect', {host: this.host, user: this.user, password: this.pass});
            document.getElementById('connection-status').innerText = `Conectado a ${this.user}@${this.host}`;
            this.renderTreeRoot(data.disks);
        } catch(e) {
            document.getElementById('login-modal').classList.remove('hidden');
        }
    }

    renderTreeRoot(disks) {
        const sidebar = document.getElementById('sidebar-tree');
        sidebar.innerHTML = '';
        disks.forEach(d => {
            const node = this.createTreeNode(d.name, d.path, true, true);
            sidebar.appendChild(node);
            // Si la unidad base estaba expandida, la forzamos
            if(this.expandedFolders.has(d.path)){
                this.toggleFolder(node.querySelector('.tree-children'), d.path, node.querySelector('.toggle'));
            }
        });
    }

    createTreeNode(name, path, isDir, isRoot = false) {
        const wrapper = document.createElement('div');
        
        const header = document.createElement('div');
        header.className = 'tree-item';
        header.dataset.path = path;
        
        const toggle = document.createElement('span');
        toggle.className = 'toggle ' + (isDir ? 'icon icon-collapsed' : '');
        
        const icon = document.createElement('span');
        icon.className = 'icon ' + (isRoot ? 'icon-disk' : (isDir ? 'icon-folder' : 'icon-file'));

        const text = document.createElement('span');
        text.innerText = name;

        header.appendChild(toggle);
        header.appendChild(icon);
        header.appendChild(text);
        wrapper.appendChild(header);

        if (isDir) {
            const childrenContainer = document.createElement('div');
            childrenContainer.className = 'tree-children';
            wrapper.appendChild(childrenContainer);

            // Click listener for expansion & loading
            header.addEventListener('click', (e) => {
                // Prevenir que un click en un hijo expanda al padre iterativamente
                e.stopPropagation(); 
                
                document.querySelectorAll('.tree-item').forEach(el => el.classList.remove('selected'));
                header.classList.add('selected');
                
                this.loadFileList(path);
                
                // Si el click fue justo en el iconito de expandir, o si queremos que todo el header expanda
                this.toggleFolder(childrenContainer, path, toggle);
            });
            
            // Auto expandir si estaba en el status
            if(this.expandedFolders.has(path) && !isRoot) {
                 this.toggleFolder(childrenContainer, path, toggle, true);
            }
        } else {
            // Es archivo, no esta en el tree usualmente, pero si estuviera
            header.addEventListener('click', () => { /* Handle file click if needed */ });
        }

        return wrapper;
    }

    async toggleFolder(container, path, toggleEl, forceLoad = false) {
        const isExpanded = container.classList.contains('expanded');
        
        if (isExpanded && !forceLoad) {
            container.classList.remove('expanded');
            toggleEl.className = 'toggle icon icon-collapsed';
            this.expandedFolders.delete(path);
            this.saveExpandedState();
            return;
        }
        
        // Expandir
        container.classList.add('expanded');
        toggleEl.className = 'toggle icon icon-expanded';
        this.expandedFolders.add(path);
        this.saveExpandedState();

        // Si ya tiene contenido, no lo volvemos a cargar (lazy)
        if (container.children.length > 0 && !forceLoad) return;

        // Mostrar loading
        container.innerHTML = '<div class="tree-item"><span class="loader"></span> Cargando...</div>';

        try {
            const data = await this.doApiCall('list', {path});
            container.innerHTML = '';
            
            const dirs = data.items.filter(i => i.is_dir).sort((a,b) => a.name.localeCompare(b.name));
            if(dirs.length === 0) {
                container.innerHTML = '<div class="empty-folder">Carpeta vacía</div>';
            } else {
                dirs.forEach(d => {
                    container.appendChild(this.createTreeNode(d.name, d.path, true));
                });
            }
        } catch(e) {
            container.innerHTML = `<div class="empty-folder" style="color:red">Error: ${e.message}</div>`;
        }
    }

    // --- Main Panel List ---
    async loadFileList(path) {
        this.currentPath = path;
        document.getElementById('current-path').innerText = path;
        const tbody = document.getElementById('file-list');
        tbody.innerHTML = '<tr><td colspan="3" style="text-align:center"><span class="loader"></span> Cargando...</td></tr>';

        try {
            const data = await this.doApiCall('list', {path});
            tbody.innerHTML = '';
            
            const dirs = data.items.filter(i => i.is_dir).sort((a,b) => a.name.localeCompare(b.name));
            const files = data.items.filter(i => !i.is_dir).sort((a,b) => a.name.localeCompare(b.name));
            const allItems = [...dirs, ...files];
            
            if(allItems.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--text-muted);">El directorio está vacío</td></tr>';
                return;
            }

            allItems.forEach(item => {
                const tr = document.createElement('tr');
                const isEditable = !item.is_dir && !NON_EDITABLE_EXTENSIONS.some(ext => item.name.toLowerCase().endsWith(ext));
                
                tr.innerHTML = `
                    <td>
                        <span class="icon ${item.is_dir ? 'icon-folder' : 'icon-file'}"></span>
                        ${item.name}
                    </td>
                    <td>${item.is_dir ? 'Carpeta' : 'Archivo'}</td>
                    <td class="actions">
                        ${!item.is_dir ? `<button class="action-btn" title="Descargar" onclick="app.downloadFile('${item.path}')"><span class="icon icon-download"></span></button>` : ''}
                        ${isEditable ? `<button class="action-btn" title="Ver" onclick="app.openViewer('${item.path}', '${item.name}')"><span class="icon icon-view"></span></button>` : ''}
                        ${isEditable ? `<button class="action-btn" title="Editar" onclick="app.openEditor('${item.path}', '${item.name}')"><span class="icon icon-edit"></span></button>` : ''}
                        <button class="action-btn" title="Eliminar" onclick="app.deleteItem('${item.path}', ${item.is_dir})"><span class="icon icon-delete"></span></button>
                    </td>
                `;
                
                if (item.is_dir) {
                    tr.addEventListener('dblclick', () => this.loadFileList(item.path));
                } else if(isEditable) {
                    tr.addEventListener('dblclick', () => this.openViewer(item.path, item.name));
                }
                
                tbody.appendChild(tr);
            });

        } catch(e) {
            tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--danger);">Error cargando: ${e.message}</td></tr>`;
        }
    }

    refreshCurrentFolder() {
        if(this.currentPath) {
            this.loadFileList(this.currentPath);
            // Si el arbol respectivo esta expandido, re-renderizarlo
            const treeEl = document.querySelector(`.tree-item[data-path="${this.currentPath}"]`);
            if(treeEl && this.expandedFolders.has(this.currentPath)) {
                this.toggleFolder(treeEl.nextElementSibling, this.currentPath, treeEl.querySelector('.toggle'), true);
            }
        }
    }

    // --- File Actions ---
    downloadCurrentFolder() {
        if(!this.currentPath) return this.showToast('Selecciona una carpeta', 'error');
        this.downloadFile(this.currentPath, true);
    }

    downloadFile(path, isDir=false) {
        // Para descargas forzamos url via query params para que se bajen como adjuntos
        const qs = new URLSearchParams({
            path, is_dir: isDir, host: this.host, user: this.user, pass: this.pass
        });
        window.location.href = `/api/download?${qs.toString()}`;
        this.showToast('Descarga iniciada...');
    }

    async deleteItem(path, isDir) {
        if(!confirm(`¿Seguro que deseas eliminar el ${isDir ? 'directorio' : 'archivo'}?\n\n${path}`)) return;
        
        try {
            await this.doApiCall('delete', {path});
            this.showToast('Eliminado correctamente', 'success');
            this.refreshCurrentFolder();
        } catch(e) { }
    }

    // --- Uploading ---
    triggerUploadModal() {
        if(!this.currentPath) return this.showToast('Selecciona una carpeta destino primero', 'error');
        document.getElementById('upload-dest-path').innerText = this.currentPath;
        document.getElementById('file-input').value = '';
        document.getElementById('upload-modal').classList.remove('hidden');
    }
    hideUploadModal() {
        document.getElementById('upload-modal').classList.add('hidden');
    }

    async uploadFiles() {
        const input = document.getElementById('file-input');
        if(!input.files.length) return this.showToast('Selecciona un archivo', 'error');
        await this.handleDropFiles(input.files);
        this.hideUploadModal();
    }

    async handleDropFiles(files) {
        if(!this.currentPath) return;
        
        this.showToast(`Subiendo ${files.length} archivo(s)...`);
        const fd = new FormData();
        fd.append('path', this.currentPath);
        for(let f of files) fd.append('file', f);

        try {
            await this.doApiCall('upload', fd);
            this.showToast('Archivos subidos con éxito', 'success');
            this.refreshCurrentFolder();
        } catch(e) { }
    }

    // --- Viewer & Editor ---
    async openFile(path, name, readOnly = false) {
        this.currentEditingFile = path;
        document.getElementById('editor-title').innerText = `${readOnly ? 'Viendo' : 'Editando'}: ${name}`;
        
        const editor = document.getElementById('file-editor');
        editor.value = 'Cargando archivo, por favor espere...';
        editor.readOnly = readOnly;
        
        const saveBtn = document.getElementById('save-btn');
        if (saveBtn) saveBtn.style.display = readOnly ? 'none' : 'inline-block';
        
        document.getElementById('editor-modal').classList.remove('hidden');

        try {
            const data = await this.doApiCall('read', {path});
            editor.value = data.content;
        } catch(e) {
            editor.value = `Error: ${e.message}`;
        }
    }

    openEditor(path, name) {
        this.openFile(path, name, false);
    }
    
    openViewer(path, name) {
        this.openFile(path, name, true);
    }

    closeEditor() {
        document.getElementById('editor-modal').classList.add('hidden');
        this.currentEditingFile = '';
    }

    async saveCurrentFile() {
        const btn = document.querySelector('#editor-modal .btn-primary');
        const originalText = btn.innerText;
        btn.innerText = 'Guardando...';
        btn.disabled = true;

        const content = document.getElementById('file-editor').value;
        const path = this.currentEditingFile;

        try {
            await this.doApiCall('save', {path, content});
            this.showToast('Archivo guardado correctamente', 'success');
            this.closeEditor();
            this.refreshCurrentFolder(); // para actualizar evt sizes o fechas si mostraramos
        } catch(e) { } finally {
            btn.innerText = originalText;
            btn.disabled = false;
        }
    }

    // --- UI Helpers ---
    showToast(msg, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        let icon = '';
        if(type === 'success') icon = '✓ ';
        else if(type === 'error') icon = '✗ ';

        toast.innerHTML = `
            <span>${icon}${msg}</span>
            <span class="toast-close" onclick="this.parentElement.remove()">✕</span>
        `;
        
        container.appendChild(toast);
        setTimeout(() => { if(toast.parentElement) toast.remove(); }, 4000);
    }
}

const app = new AppExplorer();
