(function() {
    'use strict';

    // Utility: CSRF token getter (compatible with Odoo 17)
    function getCSRFToken() {
        return (
            document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
            document.querySelector('input[name="csrf_token"]')?.value ||
            window.odoo?.csrf_token
        );
    }

    // Utility: Odoo RPC call
    async function makeRpcCall(model, method, args = [], kwargs = {}) {
        const params = {
            jsonrpc: "2.0",
            method: "call",
            params: { model, method, args, kwargs },
            id: Math.floor(Math.random() * 1000000)
        };
        const response = await fetch('/web/dataset/call_kw', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
            },
            body: JSON.stringify(params)
        });
        const data = await response.json();
        if (data.error) throw new Error(data.error.data?.message || data.error.message || 'RPC Error');
        return data.result;
    }

    // Detect if we're on the lipachat.template list view
    function isLipachatTemplateListView() {
        // Check URL for lipachat.template
        const url = window.location.href;
        if (url.includes('model=lipachat.template') || url.includes('lipachat.template')) {
            return true;
        }
        
        // Check breadcrumbs or page title
        const breadcrumbs = document.querySelector('.breadcrumb');
        if (breadcrumbs && breadcrumbs.textContent.includes('WhatsApp Templates')) {
            return true;
        }
        
        // Check for specific elements in the view
        const viewTitle = document.querySelector('.o_control_panel .o_breadcrumb_item.active');
        if (viewTitle && viewTitle.textContent.includes('WhatsApp Templates')) {
            return true;
        }
        
        return false;
    }

    // Add the fetch button above the list view
    function addFetchButton() {
        if (document.getElementById('fetch-templates-btn')) return;
        
        const controlPanel = document.querySelector('.o_control_panel');
        const listView = document.querySelector('.o_list_view');
        
        if (!controlPanel && !listView) return;

        const btnContainer = document.createElement('div');
        btnContainer.style.padding = '10px';
        btnContainer.style.borderBottom = '1px solid #dee2e6';
        
        const btn = document.createElement('button');
        btn.id = 'fetch-templates-btn';
        btn.className = 'btn btn-primary';
        btn.innerHTML = '<i class="fa fa-refresh"></i> Fetch Templates';

        btn.onclick = async function() {
            btn.disabled = true;
            btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Fetching...';
            try {
                await makeRpcCall('lipachat.template', 'action_fetch_templates', [], {});

                // Refresh the list view data
                if (window.odoo && window.odoo.define) {
                    // Try to reload the view
                    window.location.reload();
                } else {
                    window.location.reload();
                }
            } catch (e) {
                console.error('Fetch failed:', e);
                alert('Fetch failed: ' + e.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa fa-refresh"></i> Fetch Templates';
            }
        };

        btnContainer.appendChild(btn);
        
        // Insert button in the best location
        if (controlPanel) {
            controlPanel.insertAdjacentElement('afterend', btnContainer);
        } else if (listView) {
            listView.insertAdjacentElement('beforebegin', btnContainer);
        }
    }

    // Show loading state during auto-fetch
    function showLoadingState() {
        const loadingDiv = document.createElement('div');
        loadingDiv.id = 'lipachat-auto-fetch-loading';
        loadingDiv.className = 'alert alert-info';
        loadingDiv.style.margin = '10px';
        loadingDiv.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Loading WhatsApp templates...';
        
        const target = document.querySelector('.o_control_panel') || document.querySelector('.o_list_view');
        if (target) {
            target.insertAdjacentElement('afterend', loadingDiv);
        }
    }

    // Remove loading state
    function removeLoadingState() {
        const loadingDiv = document.getElementById('lipachat-auto-fetch-loading');
        if (loadingDiv) {
            loadingDiv.remove();
        }
    }

    // Auto-fetch on first load
    async function autoFetchOnLoad() {
        // Check if we already auto-fetched in this session
        const sessionKey = 'lipachat_autofetch_' + window.location.pathname;
        if (sessionStorage.getItem(sessionKey)) {
            console.log('Auto-fetch already done for this session');
            return;
        }
        
        console.log('Starting auto-fetch of templates...');
        showLoadingState();
        
        try {
            const result = await makeRpcCall('lipachat.template', 'action_fetch_templates', [], {});
            console.log('Auto-fetch successful:', result);
            
            // Mark as done for this session
            sessionStorage.setItem(sessionKey, 'done');
            
            // Reload to show fresh data
            setTimeout(() => {
                window.location.reload();
            }, 500);
            
        } catch (e) {
            console.error('Auto-fetch failed:', e);
            removeLoadingState();
            
            // Show error notification
            const notification = document.createElement('div');
            notification.className = 'alert alert-warning alert-dismissible';
            notification.style.margin = '10px';
            notification.innerHTML = `
                <button type="button" class="close" data-dismiss="alert">&times;</button>
                <strong>Notice:</strong> Could not auto-load templates. Use the "Fetch Templates" button to load manually.
            `;
            
            const target = document.querySelector('.o_control_panel') || document.querySelector('.o_list_view');
            if (target) {
                target.insertAdjacentElement('afterend', notification);
            }
        }
    }

    // Initialize when page loads
    function initializePage() {
        if (isLipachatTemplateListView()) {
            console.log('Detected lipachat template list view');
            addFetchButton();
            
            // Auto-fetch after a short delay to ensure page is fully loaded
            setTimeout(() => {
                autoFetchOnLoad();
            }, 1000);
        }
    }

    // Handle both initial load and navigation
    function handlePageLoad() {
        initializePage();
    }

    // Event listeners
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', handlePageLoad);
    } else {
        handlePageLoad();
    }

    // Also listen for URL changes (for SPA navigation)
    let currentUrl = window.location.href;
    const observer = new MutationObserver(() => {
        if (window.location.href !== currentUrl) {
            currentUrl = window.location.href;
            setTimeout(handlePageLoad, 500); // Delay to ensure DOM is updated
        }
    });

    if (document.body) {
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        observer.disconnect();
    });

})();