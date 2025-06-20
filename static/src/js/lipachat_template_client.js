(function() {
    'use strict';
    // Debug flag - set to true to see detailed logs
    const DEBUG = true;
    function log(...args) {
        if (DEBUG) console.log('[Lipachat]', ...args);
    }
    
    // Get CSRF token
    function getCSRFToken() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || 
               window.odoo?.csrf_token;
    }
    
    // Make RPC call to Odoo
    async function makeRpcCall(model, method, args = [], kwargs = {}) {
        try {
            const params = {
                jsonrpc: "2.0",
                method: "call",
                params: { model, method, args, kwargs },
                id: Math.floor(Math.random() * 1000000)
            };
            
            log(`Making RPC call to ${model}.${method}`, params);
            
            const response = await fetch('/web/dataset/call_kw', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken(),
                },
                body: JSON.stringify(params)
            });
            
            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error.data?.message || data.error.message);
            }
            
            log('RPC call successful', data.result);
            return data.result;
            
        } catch (error) {
            log('RPC call failed', error);
            throw error;
        }
    }
    
    // Enhanced page detection with more debug info
    function isTemplateListView() {
        try {
            const url = window.location.href;
            const pathname = window.location.pathname;
            const search = window.location.search;
            const hash = window.location.hash;
            
            log('Current URL:', url);
            log('Pathname:', pathname);
            log('Search params:', search);
            log('Hash:', hash);
            
            // Check URL patterns - updated to match your specific URL structure
            const urlChecks = [
                url.toLowerCase().includes('model=lipachat.template'),
                url.toLowerCase().includes('lipachat.template'),
                hash.toLowerCase().includes('model=lipachat.template'),
                // pathname.includes('/web')
            ];
            
            log('URL checks:', urlChecks);
            
            // Check DOM elements
            const breadcrumb = document.querySelector('.breadcrumb');
            const viewTitle = document.querySelector('.o_control_panel .o_breadcrumb_item.active');
            const bodyClasses = document.body.className;
            
            // log('Breadcrumb text:', breadcrumb?.textContent);
            // log('View title text:', viewTitle?.textContent);
            log('Body classes:', bodyClasses);
            
            // More flexible detection
            const isTemplate = urlChecks.some(check => check) || 
                              (breadcrumb && breadcrumb.textContent.toLowerCase().includes('template')) ||
                              (viewTitle && viewTitle.textContent.toLowerCase().includes('template'));
            
            log('Is template view:', isTemplate);
            return isTemplate;
            
        } catch (error) {
            log('Error checking template list view', error);
            return false;
        }
    }
    
    // Global variables for URL monitoring
    let currentUrl = window.location.href;
    let urlCheckInterval = null;
    let mutationObserver = null;
    
    // Enhanced URL monitoring with multiple detection methods (copied from WhatsApp chat)
    function setupUrlMonitoring() {
        // Store original URL
        currentUrl = window.location.href;
        
        // Method 1a: Override history methods
        const originalPushState = history.pushState;
        const originalReplaceState = history.replaceState;
        
        history.pushState = (...args) => {
            originalPushState.apply(history, args);
            log('PushState detected');
            setTimeout(() => handleUrlChange(), 100);
        };
        
        history.replaceState = (...args) => {
            originalReplaceState.apply(history, args);
            log('ReplaceState detected');
            setTimeout(() => handleUrlChange(), 100);
        };
        
        // Method 1b: Listen for popstate (back/forward buttons)
        window.addEventListener('popstate', () => {
            log('Popstate detected');
            setTimeout(() => handleUrlChange(), 100);
        });
        
        // Method 1c: Periodic URL checking as fallback
        urlCheckInterval = setInterval(() => {
            if (window.location.href !== currentUrl) {
                const oldUrl = currentUrl;
                currentUrl = window.location.href;
                log('Periodic check: URL changed from', oldUrl, 'to', currentUrl);
                handleUrlChange();
            }
        }, 1000);
        
        // Method 1d: DOM mutation observer for dynamic content changes
        mutationObserver = new MutationObserver((mutations) => {
            // Check if breadcrumbs or other navigation elements changed
            const hasNavigationChange = mutations.some(mutation => {
                return Array.from(mutation.addedNodes).some(node => {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        return node.querySelector && (
                            node.querySelector('.breadcrumb') ||
                            node.querySelector('.o_action_manager') ||
                            node.classList.contains('o_action_manager')
                        );
                    }
                    return false;
                });
            });
            
            if (hasNavigationChange) {
                log('DOM navigation change detected');
                setTimeout(() => handleUrlChange(), 200);
            }
        });
        
        mutationObserver.observe(document.body, {
            childList: true,
            subtree: true
        });
    }
    
    // Handle URL changes and manage session
    function handleUrlChange() {
        log('Handling URL change:', window.location.href);
        
        const isCurrentlyOnTemplatePage = isTemplateListView();
        const wasOnTemplatePage = sessionStorage.getItem('lipachat_was_on_template_page') === 'true';
        
        log('Navigation check - Currently on template page:', isCurrentlyOnTemplatePage, 'Was on template page:', wasOnTemplatePage);
        
        if (isCurrentlyOnTemplatePage) {
            // Mark that we're currently on template page
            sessionStorage.setItem('lipachat_was_on_template_page', 'true');
            log('Marked as being on template page');
            
            // Initialize if needed
            setTimeout(() => {
                handleAutoFetch();
            }, 1000);
            
        } else if (wasOnTemplatePage) {
            // We were on template page but now we're not - clear the fetch flag
            clearSessionForNavigation();
            
            // Mark that we're no longer on template page
            sessionStorage.setItem('lipachat_was_on_template_page', 'false');
            log('Navigation away from template page detected - session cleared');
        }
    }
    
    // Clear session when navigating away from template page
    function clearSessionForNavigation() {
        try {
            const allKeys = Object.keys(sessionStorage);
            
            // Clear all lipachat fetch flags
            allKeys.forEach(key => {
                if (key.startsWith('lipachat_fetched_')) {
                    sessionStorage.removeItem(key);
                    log('Cleared session key:', key);
                }
            });
            
            log('Session storage cleared due to navigation away from template page');
            
        } catch (error) {
            log('Error clearing session storage', error);
        }
    }
    
    // Show loading overlay
    function showLoading() {
        try {
            removeLoading();
            
            log('Showing loading overlay');
            
            const overlay = document.createElement('div');
            overlay.id = 'lipachat-loading-overlay';
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(255,255,255,0.9);
                z-index: 9999;
                display: flex;
                justify-content: center;
                align-items: center;
            `;
            
            const spinner = document.createElement('div');
            spinner.style.cssText = `
                text-align: center;
                padding: 20px;
                background: white;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            `;
            spinner.innerHTML = `
                <i class="fa fa-spinner fa-spin fa-3x" style="color: #007bff;"></i>
                <p style="margin: 5px 0; font-size: 1.0em; color: #666;">Please wait while we fetch your templates</p>
            `;
            
            overlay.appendChild(spinner);
            document.body.appendChild(overlay);
            
        } catch (error) {
            log('Error showing loading overlay', error);
        }
    }
    
    // Remove loading overlay
    function removeLoading() {
        try {
            const overlay = document.getElementById('lipachat-loading-overlay');
            if (overlay) {
                log('Removing loading overlay');
                overlay.remove();
            }
        } catch (error) {
            log('Error removing loading overlay', error);
        }
    }
    
    // Show notification message
    function showNotification(message, type = 'info', timeout = 5000) {
        try {
            // Remove existing notifications first
            const existing = document.querySelectorAll('.lipachat-notification');
            existing.forEach(el => el.remove());
            
            log(`Showing notification: ${message}`);
            
            const notification = document.createElement('div');
            notification.className = `alert alert-${type} alert-dismissible lipachat-notification`;
            notification.style.cssText = `
                margin: 10px;
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10000;
                max-width: 400px;
                border-radius: 6px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            `;
            
            notification.innerHTML = `
                <button type="button" class="close" onclick="this.parentElement.remove()" style="position: absolute; right: 10px; top: 10px; background: none; border: none; font-size: 20px; cursor: pointer;">&times;</button>
                <div style="padding-right: 30px;">${message}</div>
            `;
            
            document.body.appendChild(notification);
            
            // Auto-dismiss after timeout
            if (timeout > 0) {
                setTimeout(() => {
                    if (notification.parentNode) {
                        notification.remove();
                    }
                }, timeout);
            }
            
        } catch (error) {
            log('Error showing notification', error);
        }
    }

    
    // Core function to fetch templates
    async function fetchTemplates() {
        try {
            log('Starting template fetch');
            
            // Call the Odoo method to fetch templates
            const result = await makeRpcCall('lipachat.template', 'action_fetch_templates', [], {});
            
            log('Template fetch completed', result);
            return result;
            
        } catch (error) {
            log('Error fetching templates', error);
            throw new Error(`Failed to fetch templates: ${error.message}`);
        }
    }
    
    // Refresh the list view after fetching
    async function refreshListView() {
        try {
            log('Refreshing list view');
            
            // Simple page reload - most reliable method
            window.location.reload();
            
        } catch (error) {
            log('Error refreshing list view', error);
            window.location.reload();
        }
    }
    
    // Handle automatic fetch on page load
    async function handleAutoFetch() {
        try {
            // Only proceed if we're on the template page
            if (!isTemplateListView()) {
                log('Not on template page - skipping auto-fetch');
                return;
            }
            
            // Create a more specific session key based on the template page
            const sessionKey = `lipachat_fetched_${window.location.pathname}${window.location.hash}`;
            const alreadyFetched = sessionStorage.getItem(sessionKey);
            
            log('Checking auto-fetch status. Already fetched:', alreadyFetched);
            
            if (alreadyFetched) {
                log('Auto-fetch already completed for this session');
                return;
            }
            
            log('Starting auto-fetch process');
            
            // Show loading immediately
            showLoading();
            
            try {
                // Fetch templates
                await fetchTemplates();
                
                // Mark as fetched for this session
                sessionStorage.setItem(sessionKey, 'true');
                log('Marked templates as fetched in session');
                
                // Wait a bit for backend processing
                await new Promise(resolve => setTimeout(resolve, 3000));
                
                // Refresh to show the data
                log('Auto-fetch completed, refreshing page');
                window.location.reload();
                
            } catch (error) {
                log('Auto-fetch failed', error);
                removeLoading();
                showNotification(`Auto-fetch failed: ${error.message}`, 'warning', 10000);
            }
            
        } catch (error) {
            log('Error in auto-fetch handler', error);
            removeLoading();
        }
    }
    
    // Initialize the extension with retry mechanism
    function initialize() {
        try {
            log('Initializing Lipachat Template Manager');
            log('Document ready state:', document.readyState);
            log('Page URL:', window.location.href);
            
            // Set up URL monitoring first
            setupUrlMonitoring();
            
            if (isTemplateListView()) {
                log('Template list view detected, starting auto-fetch');
                
                // Wait a bit for the page to settle, then start auto-fetch
                setTimeout(() => {
                    handleAutoFetch();
                }, 1000);
                
            } else {
                log('Not a template list view, skipping auto-fetch');
            }
            
        } catch (error) {
            log('Initialization error', error);
        }
    }
    
    // Retry initialization with multiple attempts
    function initializeWithRetry() {
        let attempts = 0;
        const maxAttempts = 5;
        
        const tryInit = () => {
            attempts++;
            log(`Initialization attempt ${attempts}/${maxAttempts}`);
            
            try {
                initialize();
                log('Initialization completed');
                return;
            } catch (error) {
                log('Initialization attempt failed', error);
            }
            
            // Retry if we haven't reached max attempts
            if (attempts < maxAttempts) {
                setTimeout(tryInit, 1000);
            } else {
                log('All initialization attempts failed');
            }
        };
        
        tryInit();
    }
    
    // Cleanup function
    function cleanup() {
        if (urlCheckInterval) {
            clearInterval(urlCheckInterval);
            urlCheckInterval = null;
        }
        
        if (mutationObserver) {
            mutationObserver.disconnect();
            mutationObserver = null;
        }
    }
    
    // Start initialization
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeWithRetry);
    } else {
        initializeWithRetry();
    }
    
    // Cleanup on page unload
    window.addEventListener('beforeunload', cleanup);
    
})();