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

    // Track fetched pages to avoid duplicate fetches during the same visit
    let fetchedPages = new Set();
    let isCurrentlyFetching = false;

    // Auto-fetch on page load - fetch once per visit without reload
    async function autoFetchOnLoad() {
        const currentUrl = window.location.href;
        
        // Check if we're already fetching
        if (isCurrentlyFetching) {
            console.log('Auto-fetch already in progress, skipping...');
            return;
        }
        
        // Check if we've already fetched this URL in this visit
        if (fetchedPages.has(currentUrl)) {
            console.log('Auto-fetch already completed for this URL in current visit');
            return;
        }
        
        // Mark as being fetched
        fetchedPages.add(currentUrl);
        isCurrentlyFetching = true;
        
        console.log('Starting auto-fetch of templates...');
        showLoadingState();
        
        try {
            const result = await makeRpcCall('lipachat.template', 'action_fetch_templates', [], {});
            console.log('Auto-fetch successful:', result);
            
            // Remove loading state - no reload needed
            removeLoadingState();
            
            // Try to refresh the list view data without full page reload
            await refreshListView();
            
        } catch (e) {
            console.error('Auto-fetch failed:', e);
            removeLoadingState();
            
            // Remove from fetched pages on error so it can be retried
            fetchedPages.delete(currentUrl);
            
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
        } finally {
            isCurrentlyFetching = false;
        }
    }

    // Try to refresh the list view without full page reload
    async function refreshListView() {
        try {
            // Method 1: Try to trigger Odoo's list view refresh
            if (window.odoo && window.odoo.__DEBUG__ && window.odoo.__DEBUG__.services) {
                const actionService = window.odoo.__DEBUG__.services['action'];
                if (actionService && actionService.doAction) {
                    await actionService.doAction('reload');
                    console.log('List view refreshed via action service');
                    return;
                }
            }
            
            // Method 2: Try to find and click a refresh button
            const refreshBtn = document.querySelector('.o_cp_action_menus .o_dropdown_toggler_btn') || 
                              document.querySelector('.o_control_panel .fa-refresh') ||
                              document.querySelector('[data-hotkey="r"]');
            if (refreshBtn) {
                refreshBtn.click();
                console.log('List view refreshed via refresh button');
                return;
            }
            
            // Method 3: Fallback - show success message instead of reload
            const successDiv = document.createElement('div');
            successDiv.className = 'alert alert-success alert-dismissible';
            successDiv.style.margin = '10px';
            successDiv.innerHTML = `
                <button type="button" class="close" data-dismiss="alert">&times;</button>
                <strong>Success:</strong> Templates fetched successfully. Refresh the page to see the latest data.
            `;
            
            const target = document.querySelector('.o_control_panel') || document.querySelector('.o_list_view');
            if (target) {
                target.insertAdjacentElement('afterend', successDiv);
                
                // Auto-dismiss after 5 seconds
                setTimeout(() => {
                    if (successDiv.parentNode) {
                        successDiv.remove();
                    }
                }, 5000);
            }
            
            console.log('Fallback: showed success message');
            
        } catch (e) {
            console.error('Could not refresh list view:', e);
            // Show success message as fallback
            const successDiv = document.createElement('div');
            successDiv.className = 'alert alert-success alert-dismissible';
            successDiv.style.margin = '10px';
            successDiv.innerHTML = `
                <button type="button" class="close" data-dismiss="alert">&times;</button>
                <strong>Success:</strong> Templates fetched successfully. Refresh the page to see the latest data.
            `;
            
            const target = document.querySelector('.o_control_panel') || document.querySelector('.o_list_view');
            if (target) {
                target.insertAdjacentElement('afterend', successDiv);
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
        // Clear any existing loading states when navigating
        removeLoadingState();
        
        // Initialize the page
        setTimeout(() => {
            initializePage();
        }, 100);
    }

    // Event listeners
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', handlePageLoad);
    } else {
        handlePageLoad();
    }

    // Enhanced URL change detection for Odoo SPA navigation
    let currentUrl = window.location.href;
    
    // Method 1: MutationObserver for DOM changes
    const domObserver = new MutationObserver(() => {
        if (window.location.href !== currentUrl) {
            const oldUrl = currentUrl;
            currentUrl = window.location.href;
            console.log('URL changed from', oldUrl, 'to', currentUrl);
            setTimeout(handlePageLoad, 300);
        }
    });

    if (document.body) {
        domObserver.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    // Method 2: Listen for popstate events (browser back/forward)
    window.addEventListener('popstate', () => {
        console.log('Popstate event detected');
        setTimeout(handlePageLoad, 300);
    });

    // Method 3: Override pushState and replaceState to catch programmatic navigation
    const originalPushState = history.pushState;
    const originalReplaceState = history.replaceState;

    history.pushState = function(...args) {
        originalPushState.apply(history, args);
        console.log('PushState detected');
        setTimeout(handlePageLoad, 300);
    };

    history.replaceState = function(...args) {
        originalReplaceState.apply(history, args);
        console.log('ReplaceState detected');
        setTimeout(handlePageLoad, 300);
    };

    // Method 4: Periodic URL checking as fallback
    setInterval(() => {
        if (window.location.href !== currentUrl) {
            const oldUrl = currentUrl;
            currentUrl = window.location.href;
            console.log('Periodic check: URL changed from', oldUrl, 'to', currentUrl);
            handlePageLoad();
        }
    }, 1000);

    // Clear fetched pages when navigating away from templates
    function clearFetchedPagesIfNeeded() {
        if (!isLipachatTemplateListView()) {
            if (fetchedPages.size > 0) {
                console.log('Clearing fetched pages cache as we left template view');
                fetchedPages.clear();
                isCurrentlyFetching = false;
            }
        }
    }

    // Check periodically if we need to clear the cache
    setInterval(clearFetchedPagesIfNeeded, 2000);

    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        domObserver.disconnect();
        fetchedPages.clear();
        isCurrentlyFetching = false;
    });

})();