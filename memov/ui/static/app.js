/**
 * Memov UI Application
 * Interactive web interface for visualizing .mem git information
 */

class MemovUI {
    constructor() {
        this.currentCommit = null;
        this.currentBranch = null;
        this.commits = [];
        this.branches = [];
        this.init();
    }

    async init() {
        this.setupThemeToggle();
        this.setupBranchSelector();
        await this.loadBranches();
        await this.loadStatus();
        // Commits will be loaded after branch is selected
    }

    setupThemeToggle() {
        const toggle = document.getElementById('theme-toggle');
        const savedTheme = localStorage.getItem('memov-theme') ||
            (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');

        document.documentElement.setAttribute('data-theme', savedTheme);

        toggle.addEventListener('click', () => {
            const current = document.documentElement.getAttribute('data-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('memov-theme', next);
        });
    }

    setupBranchSelector() {
        const selector = document.getElementById('branch-selector');
        selector.addEventListener('change', async (e) => {
            const branchName = e.target.value;
            if (branchName) {
                this.currentBranch = branchName;
                this.currentCommit = null;
                await this.updateStatusForBranch(branchName);
                await this.loadCommitsForBranch(branchName);
            }
        });
    }

    async loadStatus() {
        try {
            const response = await fetch('/api/status');
            const status = await response.json();

            document.getElementById('project-path').textContent = status.project_path;
            document.getElementById('project-path').title = status.project_path;

            // Initial status will be updated when branch is selected
            if (this.currentBranch) {
                await this.updateStatusForBranch(this.currentBranch);
            } else {
                document.getElementById('head-commit').textContent = status.head || 'N/A';
                document.getElementById('current-branch').textContent = status.current_branch || 'detached';
            }
        } catch (error) {
            console.error('Failed to load status:', error);
            document.getElementById('head-commit').textContent = 'Error';
            document.getElementById('current-branch').textContent = 'Error';
        }
    }

    async updateStatusForBranch(branchName) {
        try {
            const response = await fetch(`/api/branches/${encodeURIComponent(branchName)}`);
            const branchInfo = await response.json();

            document.getElementById('head-commit').textContent = branchInfo.commit || 'N/A';
            document.getElementById('current-branch').textContent = branchName;
        } catch (error) {
            console.error('Failed to load branch info:', error);
        }
    }

    async loadBranches() {
        try {
            const response = await fetch('/api/branches');
            const data = await response.json();

            this.branches = data.branches || [];
            const selector = document.getElementById('branch-selector');

            if (this.branches.length > 0) {
                selector.innerHTML = this.branches.map(b =>
                    `<option value="${this.escapeHtml(b.name)}" ${b.name === data.current ? 'selected' : ''}>
                        ${this.escapeHtml(b.name)} (${b.commit})
                    </option>`
                ).join('');

                // Set current branch and load its commits
                this.currentBranch = data.current || this.branches[0].name;
                await this.updateStatusForBranch(this.currentBranch);
                await this.loadCommitsForBranch(this.currentBranch);
            } else {
                selector.innerHTML = '<option value="">No branches</option>';
                this.showEmptyState();
            }
        } catch (error) {
            console.error('Failed to load branches:', error);
            document.getElementById('branch-selector').innerHTML =
                '<option value="">Error loading</option>';
        }
    }

    async loadCommitsForBranch(branchName) {
        const container = document.getElementById('commits-list');
        container.innerHTML = `
            <div class="loading">
                <div class="spinner"></div>
                <span>Loading commits...</span>
            </div>
        `;

        try {
            const response = await fetch(`/api/commits?limit=100&branch=${encodeURIComponent(branchName)}`);
            this.commits = await response.json();
            this.renderCommitsList();
        } catch (error) {
            console.error('Failed to load commits:', error);
            container.innerHTML = `
                <div class="loading">
                    <span>Failed to load commits</span>
                </div>
            `;
        }
    }

    showEmptyState() {
        const container = document.getElementById('commits-list');
        container.innerHTML = `
            <div class="loading">
                <span>No commits found</span>
            </div>
        `;

        document.getElementById('commit-detail').innerHTML = `
            <div class="empty-state">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
                </svg>
                <p>No commits to display</p>
            </div>
        `;
    }

    renderCommitsList() {
        const container = document.getElementById('commits-list');

        if (this.commits.length === 0) {
            container.innerHTML = `
                <div class="loading">
                    <span>No commits in this branch</span>
                </div>
            `;
            return;
        }

        container.innerHTML = this.commits.map(commit => `
            <div class="commit-item" data-hash="${commit.hash}">
                <div class="commit-header">
                    <span class="commit-hash">${commit.short_hash}</span>
                </div>
                <div class="commit-message">${this.escapeHtml(commit.message)}</div>
                <div class="commit-meta">
                    <span class="operation-badge ${commit.operation_type}">${commit.operation_type}</span>
                    <span class="file-count">
                        <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0113.25 16h-9.5A1.75 1.75 0 012 14.25Zm1.75-.25a.25.25 0 00-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 00.25-.25V6h-2.75A1.75 1.75 0 019 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688l-.011-.013-2.914-2.914-.013-.011Z"/>
                        </svg>
                        ${commit.file_count} file${commit.file_count !== 1 ? 's' : ''}
                    </span>
                    ${commit.source ? `<span>${this.escapeHtml(commit.source)}</span>` : ''}
                </div>
            </div>
        `).join('');

        // Add click handlers
        container.querySelectorAll('.commit-item').forEach(item => {
            item.addEventListener('click', () => {
                this.selectCommit(item.dataset.hash);
            });
        });

        // Auto-select first commit
        if (this.commits.length > 0 && !this.currentCommit) {
            this.selectCommit(this.commits[0].hash);
        }
    }

    async selectCommit(hash) {
        this.currentCommit = hash;

        // Update active state
        document.querySelectorAll('.commit-item').forEach(item => {
            item.classList.toggle('active', item.dataset.hash === hash);
        });

        const container = document.getElementById('commit-detail');
        container.innerHTML = `
            <div class="loading">
                <div class="spinner"></div>
                <span>Loading commit details...</span>
            </div>
        `;

        try {
            const response = await fetch(`/api/commits/${hash}`);
            const commit = await response.json();

            if (commit.error) {
                throw new Error(commit.error);
            }

            this.renderCommitDetail(commit);
        } catch (error) {
            console.error('Failed to load commit detail:', error);
            container.innerHTML = `
                <div class="empty-state">
                    <p>Failed to load commit details</p>
                </div>
            `;
        }
    }

    renderCommitDetail(commit) {
        const container = document.getElementById('commit-detail');

        const sections = [];

        // Header
        sections.push(`
            <div class="detail-header">
                <h2>${this.escapeHtml(commit.message)}</h2>
                <span class="detail-hash">${commit.hash}</span>
            </div>
        `);

        // Metadata
        sections.push(`
            <div class="detail-section">
                <h3>
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M0 1.75A.75.75 0 01.75 1h4.253c1.227 0 2.317.59 3 1.501A3.743 3.743 0 0111.006 1h4.245a.75.75 0 01.75.75v10.5a.75.75 0 01-.75.75h-4.507a2.25 2.25 0 00-1.591.659l-.622.621a.75.75 0 01-1.06 0l-.622-.621A2.25 2.25 0 005.258 13H.75a.75.75 0 01-.75-.75Zm7.251 10.324l.004-5.073-.002-2.253A2.25 2.25 0 005.003 2.5H1.5v9h3.757a3.75 3.75 0 011.994.574ZM8.755 4.75l-.004 7.322a3.752 3.752 0 011.992-.572H14.5v-9h-3.495a2.25 2.25 0 00-2.25 2.25Z"/>
                    </svg>
                    Metadata
                </h3>
                <div class="metadata-grid">
                    <span class="metadata-label">Operation</span>
                    <span class="metadata-value">
                        <span class="operation-badge ${commit.operation_type}">${commit.operation_type}</span>
                    </span>
                    <span class="metadata-label">Source</span>
                    <span class="metadata-value">${this.escapeHtml(commit.source) || 'N/A'}</span>
                    <span class="metadata-label">Files</span>
                    <span class="metadata-value">${commit.file_count} file(s)</span>
                </div>
            </div>
        `);

        // Prompt
        if (commit.prompt) {
            sections.push(`
                <div class="detail-section">
                    <h3>
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M6.749.097a8.054 8.054 0 012.502 0 .75.75 0 11-.233 1.482 6.554 6.554 0 00-2.036 0A.75.75 0 016.749.097ZM3.616 1.62a.75.75 0 01.058 1.06 6.558 6.558 0 00-1.44 1.44.75.75 0 11-1.177-.93 8.058 8.058 0 011.5-1.512.75.75 0 011.059-.058Zm8.768 0a.75.75 0 011.06.058 8.058 8.058 0 011.5 1.512.75.75 0 01-1.178.93 6.558 6.558 0 00-1.44-1.44.75.75 0 01.058-1.06ZM.097 6.749a.75.75 0 01.882-.604 6.554 6.554 0 002.036 0 .75.75 0 01.233 1.482 8.054 8.054 0 01-2.502 0 .75.75 0 01-.65-.878ZM16 8a.75.75 0 01-.75.75 6.554 6.554 0 000 2.036.75.75 0 11-1.482.233 8.054 8.054 0 010-2.502A.75.75 0 0116 8Zm-13.978.75a.75.75 0 01-.75-.75.75.75 0 01.75-.75 6.554 6.554 0 000-2.036.75.75 0 111.482-.233 8.054 8.054 0 010 2.502.75.75 0 01-.75.75.75.75 0 01-.732.517ZM1.62 12.384a.75.75 0 011.06-.058 6.558 6.558 0 001.44 1.44.75.75 0 01-.93 1.177 8.058 8.058 0 01-1.512-1.5.75.75 0 01-.058-1.06Zm12.76 0a.75.75 0 01-.058 1.06 8.058 8.058 0 01-1.512 1.5.75.75 0 01-.93-1.178 6.558 6.558 0 001.44-1.44.75.75 0 011.06.058ZM6.749 15.903a8.054 8.054 0 002.502 0 .75.75 0 11.233 1.482 9.554 9.554 0 01-2.968 0 .75.75 0 01.233-1.482Z"/>
                        </svg>
                        Prompt
                    </h3>
                    <div class="content-box prompt-box">${this.escapeHtml(commit.prompt)}</div>
                </div>
            `);
        }

        // Response
        if (commit.response) {
            sections.push(`
                <div class="detail-section">
                    <h3>
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M1.5 3.25c0-.966.784-1.75 1.75-1.75h10.5c.966 0 1.75.784 1.75 1.75v7.5A1.75 1.75 0 0113.75 12.5h-3.72l-2.03 2.03a.75.75 0 01-1.06 0l-2.03-2.03H1.75A1.75 1.75 0 010 10.75v-7.5zm1.75-.25a.25.25 0 00-.25.25v7.5c0 .138.112.25.25.25h3.5a.75.75 0 01.53.22L8 12.69l2.22-2.22a.75.75 0 01.53-.22h3.5a.25.25 0 00.25-.25v-7.5a.25.25 0 00-.25-.25H3.25z"/>
                        </svg>
                        Response
                    </h3>
                    <div class="content-box response-box">${this.escapeHtml(commit.response)}</div>
                </div>
            `);
        }

        // Agent Plan
        if (commit.agent_plan) {
            sections.push(`
                <div class="detail-section">
                    <h3>
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M2 3.75C2 2.784 2.784 2 3.75 2h8.5c.966 0 1.75.784 1.75 1.75v8.5A1.75 1.75 0 0112.25 14h-8.5A1.75 1.75 0 012 12.25Zm1.75-.25a.25.25 0 00-.25.25v8.5c0 .138.112.25.25.25h8.5a.25.25 0 00.25-.25v-8.5a.25.25 0 00-.25-.25ZM8 10a1 1 0 100-2 1 1 0 000 2Z"/>
                        </svg>
                        Agent Plan
                    </h3>
                    <div class="content-box plan-box">${this.escapeHtml(commit.agent_plan)}</div>
                </div>
            `);
        }

        // Files Changed
        if (commit.files && commit.files.length > 0) {
            sections.push(`
                <div class="detail-section">
                    <h3>
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0113.25 16h-9.5A1.75 1.75 0 012 14.25Zm1.75-.25a.25.25 0 00-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 00.25-.25V6h-2.75A1.75 1.75 0 019 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688l-.011-.013-2.914-2.914-.013-.011Z"/>
                        </svg>
                        Files Changed (${commit.files.length})
                    </h3>
                    <ul class="file-list">
                        ${commit.files.map(f => `<li>${this.escapeHtml(f)}</li>`).join('')}
                    </ul>
                </div>
            `);
        }

        // Diff
        if (commit.diff) {
            sections.push(`
                <div class="detail-section">
                    <h3>
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M8.75 1.75V5H12a.75.75 0 010 1.5H8.75v3.25a.75.75 0 01-1.5 0V6.5H4A.75.75 0 014 5h3.25V1.75a.75.75 0 011.5 0zM4 13h8a.75.75 0 010 1.5H4A.75.75 0 014 13z"/>
                        </svg>
                        Diff
                    </h3>
                    <div class="diff-container">
                        <div class="diff-content">
                            ${this.renderDiff(commit.diff)}
                        </div>
                    </div>
                </div>
            `);
        }

        container.innerHTML = sections.join('');
    }

    renderDiff(diff) {
        if (!diff) return '<div class="diff-line">No diff available</div>';

        const lines = diff.split('\n');
        let lineNumber = 0;
        let inHunk = false;

        return lines.map(line => {
            let className = 'diff-line';
            let content = line;

            if (line.startsWith('+++') || line.startsWith('---')) {
                className += ' meta';
                inHunk = false;
            } else if (line.startsWith('@@')) {
                className += ' hunk';
                inHunk = true;
                // Parse line numbers from hunk header
                const match = line.match(/@@ -\d+(?:,\d+)? \+(\d+)/);
                if (match) {
                    lineNumber = parseInt(match[1], 10) - 1;
                }
            } else if (line.startsWith('diff ') || line.startsWith('index ') ||
                       line.startsWith('new file') || line.startsWith('deleted file')) {
                className += ' meta';
                inHunk = false;
            } else if (line.startsWith('+')) {
                className += ' add';
                if (inHunk) lineNumber++;
            } else if (line.startsWith('-')) {
                className += ' remove';
            } else if (inHunk) {
                lineNumber++;
            }

            const lineNumStr = (className.includes('add') || (!className.includes('remove') && !className.includes('meta') && !className.includes('hunk') && inHunk))
                ? lineNumber.toString()
                : '';

            if (className.includes('hunk') || className.includes('meta')) {
                return `<div class="${className}">${this.escapeHtml(content)}</div>`;
            }

            return `<div class="${className}">
                <span class="diff-line-number">${lineNumStr}</span>
                <span class="diff-line-content">${this.escapeHtml(content)}</span>
            </div>`;
        }).join('');
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.memovUI = new MemovUI();
});
