// static/src/js/whatsapp_chat_client.js
// Optimized Vanilla JavaScript version

(function() {
    'use strict';

    class WhatsAppChatClient {
        constructor() {
            this.currentSelectedPartnerId = null;
            this.currentSelectedContactName = null;
            this.autoRefreshInterval = null;
            this.lastMessageId = 0;
            this.isInitialized = false;
            this.isSending = false;
            this.eventListeners = [];
            this.initPromise = null; // Track initialization promise
            this.sessionTimer = null;
            this.sessionInfo = {};
            this.sessionTimerInterval = null;
            this.sessionEndCallback = null;
            this.currentUrl = window.location.href;
            this.urlCheckInterval = null;
            this.mutationObserver = null;
        }

        addEventListener(element, event, handler) {
            if (!element || !event || !handler) {
                console.error('Invalid arguments for addEventListener', {element, event, handler});
                return;
            }
            
            element.addEventListener(event, handler);
            this.eventListeners.push({ element, event, handler });
        }

        getCSRFToken() {
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
                            document.querySelector('input[name="csrf_token"]')?.value ||
                            window.odoo?.csrf_token;
            return csrfToken;
        }

        findOdooField(fieldName) {
            const selectors = [
                `input[name="${fieldName}"]`,
                `[name="${fieldName}"]`,
                `input[data-field-name="${fieldName}"]`,
                `[data-field-name="${fieldName}"]`,
                `.o_field_widget[name="${fieldName}"] input`,
                `.o_field_widget[name="${fieldName}"] textarea`,
                `#${fieldName}`,
                `.o_field_${fieldName} input`
            ];

            for (const selector of selectors) {
                const element = document.querySelector(selector);
                if (element) return element;
            }
            return null;
        }

        async makeRpcCall(model, method, args = [], kwargs = {}) {
            const params = {
                jsonrpc: "2.0",
                method: "call",
                params: {
                    model: model,
                    method: method,
                    args: args,
                    kwargs: kwargs
                },
                id: Math.floor(Math.random() * 1000000)
            };

            const response = await fetch('/web/dataset/call_kw', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken(),
                },
                body: JSON.stringify(params)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (data.error) {
                console.error('RPC Error Details:', data.error);
                throw new Error(data.error.data?.message || data.error.message || 'RPC Error');
            }

            return data.result;
        }

        renderMessages(messagesHtml) {
            const messagesContainer = document.getElementById('chat-messages-container');
            if (messagesContainer) {
                messagesContainer.innerHTML = messagesHtml;
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
        }

        updateOdooFields(partnerId, contactName) {
            const contactField = this.findOdooField('contact');
            if (contactField) {
                contactField.value = contactName;
                contactField.dispatchEvent(new Event('input', { bubbles: true }));
                contactField.dispatchEvent(new Event('change', { bubbles: true }));
            }
        
            const partnerIdField = this.findOdooField('contact_partner_id');
            if (partnerIdField) {
                partnerIdField.value = partnerId;
                partnerIdField.dispatchEvent(new Event('input', { bubbles: true }));
                partnerIdField.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }

        async selectContact(partnerId, contactName) {
            try {
                partnerId = parseInt(partnerId);
                if (isNaN(partnerId)) {
                    console.error('Invalid partner ID:', partnerId);
                    return;
                }
            
                this.currentSelectedPartnerId = partnerId;
                this.currentSelectedContactName = contactName || `Contact ${partnerId}`;
                this.lastMessageId = 0;
            
                this.updateContactSelectionUI(partnerId);
                this.updateChatHeader(this.currentSelectedContactName);
                this.updateOdooFields(partnerId, this.currentSelectedContactName);
                
                // Check session status first
                const sessionInfo = await this.checkSessionStatus(partnerId);
                this.updateInputFields(sessionInfo, partnerId);
                
                // Then load messages
                const messagesHtml = await this.makeRpcCall(
                    'whatsapp.chat',
                    'rpc_get_messages_html',
                    [partnerId]
                );
                this.renderMessages(messagesHtml);
                
                // If session is active, set up expiration callback
                if (sessionInfo.active) {
                    this.sessionEndCallback = () => {
                        this.showChatInfo('Session has expired');
                        this.checkSessionStatus(partnerId); // Refresh session status
                    };
                }
                
            } catch (error) {
                console.error("Error in selectContact:", error);
                this.renderMessages(`
                    <div class="chat-error">
                        Failed to load conversation: ${error.message}
                    </div>
                `);
            }
        }

        updateChatHeader(contactName) {
            const chatHeader = document.getElementById('chat-header-contact-name');
            if (chatHeader) {
                chatHeader.textContent = contactName;
            }
        }

        getMessageText() {
            const messageInput = document.querySelector('textarea[name="new_message"]') ||
                               document.querySelector('.o_whatsapp_new_message textarea') ||
                               document.querySelector('.o_whatsapp_new_message') ||
                               this.findOdooField('new_message');
            
            if (messageInput) {
                return messageInput.value ? messageInput.value.trim() : '';
            }
            return '';
        }

        async handleSendMessage() {
            if (this.isSending) return;
            this.isSending = true;
            
            try {
                const messageInput = document.querySelector('textarea[name="new_message"]') ||
                                document.querySelector('.o_whatsapp_new_message textarea') ||
                                document.querySelector('.o_whatsapp_new_message') ||
                                this.findOdooField('new_message');
                
                if (!messageInput) {
                    console.error("Message input element not found!");
                    return;
                }

                const messageText = messageInput.value.trim();
                
                if (!this.currentSelectedPartnerId) {
                    this.showChatError('Please select a contact first');
                    return;
                }

                if (!messageText) {
                    this.showChatError('Please enter a message');
                    return;
                }

                this.showSendingStatus(true);

                const result = await this.makeRpcCall(
                    'whatsapp.chat',
                    'rpc_send_message',
                    [parseInt(this.currentSelectedPartnerId), messageText]
                );

                messageInput.value = '';
                messageInput.dispatchEvent(new Event('change', { bubbles: true }));
                messageInput.dispatchEvent(new Event('input', { bubbles: true }));

                await this.selectContact(this.currentSelectedPartnerId, this.currentSelectedContactName);

                if (result && result.status === 'success') {
                    this.showChatSuccess(result.message);
                     // Check if session was started
                        if (result.session_started) {
                            setTimeout(() => {
                                this.checkSessionStatus(this.currentSelectedPartnerId);
                            }, 1000); // Small delay to ensure session is saved
                        }
              }

            } catch (error) {
                console.error("Error sending message:", error);
                this.showChatError(error.message || 'Failed to send message');
            } finally {
                this.showSendingStatus(false);
                this.isSending = false;
            }
        }

        showChatSuccess(message) {
            const messagesContainer = document.getElementById('chat-messages-container');
            if (messagesContainer) {
                const successDiv = document.createElement('div');
                successDiv.className = 'chat-success-message';
                successDiv.style.cssText = 'color: green; padding: 10px; text-align: center; background: #d4edda; border-radius: 4px; margin: 10px;';
                successDiv.textContent = message;
                messagesContainer.appendChild(successDiv);
                setTimeout(() => successDiv.remove(), 3000);
            }
        }
        
        showChatError(message) {
            const messagesContainer = document.getElementById('chat-messages-container');
            if (messagesContainer) {
                const errorDiv = document.createElement('div');
                errorDiv.className = 'chat-error-message';
                errorDiv.style.cssText = 'color: red; padding: 10px; text-align: center; background: #ffebee; border-radius: 4px; margin: 10px;';
                errorDiv.textContent = message;
                messagesContainer.appendChild(errorDiv);
                setTimeout(() => errorDiv.remove(), 3000);
            }
        }
        
        showSendingStatus(isSending) {
            const sendButton = document.querySelector('.o_whatsapp_send_button');
            if (sendButton) {
                if (isSending) {
                    sendButton.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Sending...';
                    sendButton.disabled = true;
                } else {
                    sendButton.innerHTML = '<i class="fa fa-paper-plane"></i> Send';
                    sendButton.disabled = false;
                }
            }
        }

        showLoadingState(isLoading) {
            const container = document.querySelector('.chat-container');
            if (container) {
                if (isLoading) {
                    container.classList.add('loading');
                } else {
                    container.classList.remove('loading');
                }
            }
        }

        async updateContactsList() {
            try {
                const contactsHtml = await this.makeRpcCall(
                    'whatsapp.chat',
                    'rpc_get_contacts_html',
                    [],
                    {}
                );
                
                const contactsContainer = document.querySelector('.chat-contacts .contacts-list') ||
                                        document.querySelector('.o_whatsapp_contacts_html');
                if (contactsContainer) {
                    contactsContainer.innerHTML = contactsHtml;
                    if (this.currentSelectedPartnerId) {
                        this.updateContactSelectionUI(this.currentSelectedPartnerId);
                    }
                }
            } catch (error) {
                console.error("Error updating contacts list:", error);
            }
        }

        startAutoRefresh() {
            if (this.autoRefreshInterval) {
                clearInterval(this.autoRefreshInterval);
            }
            this.autoRefreshInterval = setInterval(async () => {
                if (document.visibilityState === 'visible') { 
                    if (this.currentSelectedPartnerId) {
                        await this.selectContact(this.currentSelectedPartnerId, this.currentSelectedContactName);
                    }
                    await this.updateContactsList();
                }
            }, 10000);
        }

        setupMessageInput() {
            const messageInput = this.findOdooField('new_message') || 
                                document.querySelector('textarea[name="new_message"]') ||
                                document.querySelector('.o_whatsapp_new_message textarea') ||
                                document.querySelector('.o_whatsapp_new_message');
            
            if (messageInput) {
                this.addEventListener(messageInput, 'keydown', (event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        event.stopPropagation();
                        this.handleSendMessage();
                    }
                });
        
                this.addEventListener(messageInput, 'input', () => {
                    messageInput.style.height = 'auto';
                    messageInput.style.height = messageInput.scrollHeight + 'px';
                });
            }
        }

        updateContactSelectionUI(partnerId) {
            document.querySelectorAll('.contact-item').forEach(item => {
                item.style.backgroundColor = 'white';
                item.style.border = '1px solid #eee';
                item.classList.remove('selected');
            });
            
            const selectedItem = document.querySelector(`.contact-item[data-partner-id="${partnerId}"]`);
            if (selectedItem) {
                selectedItem.style.backgroundColor = '#e8f5e8';
                selectedItem.style.border = '2px solid #25D366';
                selectedItem.classList.add('selected');
                selectedItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }

        // OPTIMIZED: Pre-load the most recent contact immediately
        async preloadRecentContact() {
            try {
                // First try to get initial data from server
                const initialData = await this.makeRpcCall(
                    'whatsapp.chat', 
                    'get_initial_chat_data',
                    []
                );
        
                if (initialData.partner_id) {
                    // We have everything we need - update UI immediately
                    this.currentSelectedPartnerId = initialData.partner_id;
                    this.currentSelectedContactName = initialData.partner_name;
                    this.updateOdooFields(initialData.partner_id, initialData.partner_name);
                    this.updateChatHeader(initialData.partner_name);
                    
                    // Render pre-loaded content
                    const contactsContainer = document.querySelector('.chat-contacts .contacts-list') ||
                                            document.querySelector('.o_whatsapp_contacts_html');
                    if (contactsContainer && initialData.contacts_html) {
                        contactsContainer.innerHTML = initialData.contacts_html;
                    }
                    
                    if (initialData.messages_html) {
                        this.renderMessages(initialData.messages_html);
                    }
                    
                    return; // We're done
                }
        
                // Fallback to individual RPC calls if no initial data
                const result = await this.makeRpcCall('whatsapp.chat', 'get_most_recent_contact', []);
                if (result && result.partner_id) {
                    await this.selectContact(result.partner_id, result.name);
                }
            } catch (error) {
                console.error("Error preloading recent contact:", error);
            }
        }

        updateInputFields(sessionInfo, partnerId) {
            const hasContact = !!partnerId;
            const isSessionActive = sessionInfo.active;

            console.log("Contact is selected: " + hasContact)
            console.log("Contact session is active: " + isSessionActive)
            
            // Normal message input (shown when session is active AND contact is selected)
            const normalInput = document.getElementById('normal-message-input');
            if (normalInput) {
                normalInput.style.display = (isSessionActive && hasContact) ? 'flex' : 'none';
            }
            
            // Template message section (shown when session is NOT active AND contact is selected)
            const templateSection = document.querySelector('.template-message-group');
            if (templateSection) {
                templateSection.style.display = (!isSessionActive && hasContact) ? 'block' : 'none';
            }
            
            // If no contact is selected, hide both
            if (!hasContact) {
                if (normalInput) normalInput.style.display = 'none';
                if (templateSection) templateSection.style.display = 'none';
            }
        }

        

        async checkSessionStatus(partnerId) {
            try {
                const sessionInfo = await this.makeRpcCall(
                    'whatsapp.chat',
                    'rpc_get_session_info',
                    [partnerId]
                );
                
                this.sessionInfo = sessionInfo;
                this.updateSessionUI(sessionInfo);

                this.updateInputFields(sessionInfo, partnerId);
                
                return sessionInfo;
            } catch (error) {
                console.error("Error checking session status:", error);
                return { active: false };
            }
        }

        updateSessionUI(sessionInfo) {
            const sessionContainer = document.getElementById('session-timer-container');
            const onlineIndicator = document.querySelector('.online-indicator');
            
            if (!sessionContainer || !onlineIndicator) return;
            
            if (sessionInfo.active) {
                sessionContainer.style.display = 'inline-block';
                onlineIndicator.style.backgroundColor = '#25D366';
                if (sessionInfo.remaining_time > 0) {
                    this.startSessionTimer(sessionInfo.remaining_time);
                } else {
                    this.stopSessionTimer();
                }
            } else {
                sessionContainer.style.display = 'none';
                onlineIndicator.style.backgroundColor = '#ccc';
                this.stopSessionTimer();
            }
        }


        startSessionTimer(remainingSeconds) {
            this.stopSessionTimer(); // Clear any existing timer
            
            // Update immediately
            this.updateTimerDisplay(remainingSeconds);
            
            // Start interval
            this.sessionTimerInterval = setInterval(() => {
                remainingSeconds--;
                this.updateTimerDisplay(remainingSeconds);
                
                if (remainingSeconds <= 0) {
                    this.stopSessionTimer();
                    if (this.sessionEndCallback) {
                        this.sessionEndCallback();
                    }
                }
            }, 1000);
        }

        updateTimerDisplay(seconds) {
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = seconds % 60;
            const timeString = `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
            
            const timerDisplay = document.getElementById('session-timer-display');
            if (timerDisplay) {
                timerDisplay.textContent = timeString;
            }
        }


        stopSessionTimer() {
            if (this.sessionTimerInterval) {
                clearInterval(this.sessionTimerInterval);
                this.sessionTimerInterval = null;
            }
        }
        
        onSessionExpired() {
            const sessionContainer = document.getElementById('session-timer-container');
            if (sessionContainer) {
                sessionContainer.style.display = 'none';
            }
            
            // Optionally show a notification
            this.showChatInfo('Session expired');
        }

        showChatInfo(message) {
            const messagesContainer = document.getElementById('chat-messages-container');
            if (messagesContainer) {
                const infoDiv = document.createElement('div');
                infoDiv.className = 'chat-info-message';
                infoDiv.style.cssText = 'color: #666; padding: 10px; text-align: center; background: #f0f0f0; border-radius: 4px; margin: 10px; font-style: italic;';
                infoDiv.textContent = message;
                messagesContainer.appendChild(infoDiv);
                setTimeout(() => infoDiv.remove(), 3000);
            }
        }
        
        



        // OPTIMIZED: Initialize with minimal DOM dependency
        async initialize() {
            if (this.isInitialized || this.initPromise) {
                return this.initPromise;
            }

            this.initPromise = this._doInitialize();
            return this.initPromise;
        }



        async loadTemplates() {
            try {
                const templates = await this.makeRpcCall(
                    'whatsapp.chat',
                    'get_available_templates',
                    []
                );
                
                // You can use this data to enhance the UI if needed
                return templates;
            } catch (error) {
                console.error("Error loading templates:", error);
                return [];
            }
        }

        // async handleSendTemplate() {
        //     if (this.isSending) return;
        //     this.isSending = true;
        
        //     try {
                
        //         const templateField = document.querySelector('.o_field_many2one input') || 
        //                             document.querySelector('.o_field_widget[name="template_id"] input');
        //         const templateId = templateField && templateField.value ? templateField.value : null;
                
        //         // if (!this.currentSelectedPartnerId) {
        //         //     this.showChatError('Please select a contact first');
        //         //     return;
        //         // }
        
        //         if (!templateId) {
        //             this.showChatError('Please select a template');
        //             return;
        //         }
        
        //         // Check if we need a media URL
        //         const mediaUrlField = document.querySelector('input[name="template_media_url"]');
        //         let mediaUrl = null;
                
        //         if (mediaUrlField && mediaUrlField.style.display !== 'none') {
        //             mediaUrl = mediaUrlField.value.trim();
        //             if (!mediaUrl) {
        //                 this.showChatError('Please enter a media URL for this template');
        //                 return;
        //             }
        //         }
        
        //         this.showSendingStatus(true);
        
        //         const result = await this.makeRpcCall(
        //             'whatsapp.chat',
        //             'send_template_message',
        //             [templateId, parseInt(this.currentSelectedPartnerId), mediaUrl]
        //         );
        
        //         if (result && result.status === 'success') {
        //             this.showChatSuccess(result.message);
        //             await this.selectContact(this.currentSelectedPartnerId, this.currentSelectedContactName);
        //         }
        
        //     } catch (error) {
        //         console.error("Error sending template message:", error);
        //         this.showChatError(error.message || 'Failed to send template message');
        //     } finally {
        //         this.showSendingStatus(false);
        //         this.isSending = false;
        //     }
        // }


        async handleSendTemplate() {
            if (this.isSending) return;
            this.isSending = true;
        
            try {
                
                const templateField = document.querySelector('.o_field_many2one input') || 
                                    document.querySelector('.o_field_widget[name="template_id"] input');

                const templateId = templateField ? templateField.value : null;


                console.log("Hello world. Clicked send temp message button!")
                console.log("Template ID:", templateId);
                
                if (!this.currentSelectedPartnerId) {
                    this.showChatError('Please select a contact first');
                    return;
                }
        
                if (!templateId) {
                    this.showChatError('Please select a template');
                    return;
                }
        
                // Check if we need a media URL
                const mediaUrlField = document.querySelector('.o_field_widget[name="template_media_url"] input');
                let mediaUrl = null;
                
                if (mediaUrlField && mediaUrlField.style.display !== 'none') {
                    mediaUrl = mediaUrlField.value.trim();
                    if (!mediaUrl) {
                        this.showChatError('Please enter a media URL for this template');
                        return;
                    }
                }

                // Get placeholder values
                const placeholderField = document.querySelector('.o_field_widget[name="template_variable_values"] input');
                let variableValues = [];
                if (placeholderField && placeholderField.value.trim() !== '') {
                    variableValues = placeholderField.value.split(',').map(item => item.trim());
                }
                console.log(variableValues);
    
                this.showSendingStatus(true);
        
                const result = await this.makeRpcCall(
                    'whatsapp.chat',
                    'send_template_message_v2',
                    [ parseInt(this.currentSelectedPartnerId), parseInt(this.currentSelectedPartnerId), templateId, variableValues, mediaUrl ]
                );
        
                if (result && result.status === 'success') {
                    this.showChatSuccess(result.message);
                    await this.selectContact(this.currentSelectedPartnerId, this.currentSelectedContactName);
                }
        
            } catch (error) {
                console.error("Error sending template message:", error);
                this.showChatError(error.message || 'Failed to send template message');
            } finally {
                this.showSendingStatus(false);
                this.isSending = false;
            }
        }

        setupTemplateSelection() {
            const templateField = document.querySelector('input[name="template_id"]') || 
                                 document.querySelector('.o_field_many2one[name="template_id"]');
            
            if (templateField) {
                this.addEventListener(templateField, 'change', async (event) => {
                    // Get the selected template details
                    const templateId = templateField.value ? parseInt(templateField.value) : null;
                    if (templateId) {
                        const templates = await this.loadTemplates();
                        const selectedTemplate = templates.find(t => t.id === templateId);
                        
                        if (selectedTemplate) {
                            // Show/hide media URL field based on header type
                            const mediaUrlField = document.querySelector('input[name="template_media_url"]');
                            const mediaUrlContainer = document.querySelector('.template-media-url-container');
                            
                            if (selectedTemplate.header_type === 'media') {
                                if (mediaUrlContainer) mediaUrlContainer.style.display = 'block';
                                if (mediaUrlField) mediaUrlField.required = true;
                            } else {
                                if (mediaUrlContainer) mediaUrlContainer.style.display = 'none';
                                if (mediaUrlField) mediaUrlField.required = false;
                            }
                        }
                    }
                });
            }
        }


        // hideInputsOnLoad() {
        //     // Try multiple times to ensure elements exist
        //     const hideInputs = () => {
        //         const normalInput = document.getElementById('normal-message-input');
        //         const templateSection = document.getElementById('template-message-input');
                
        //         console.log('Attempting to hide inputs:', { normalInput: !!normalInput, templateSection: !!templateSection });
                
        //         if (normalInput) {
        //             normalInput.style.display = 'none';
        //             console.log('Hidden normal input');
        //         }
        //         if (templateSection) {
        //             templateSection.style.display = 'none';
        //             console.log('Hidden template section');
        //         }
                
        //         // If elements still don't exist, try again after a short delay
        //         if (!normalInput || !templateSection) {
        //             setTimeout(hideInputs, 100);
        //         }
        //     };
            
        //     // Try immediately
        //     hideInputs();
            
        //     // Also try after a short delay
        //     setTimeout(hideInputs, 50);
        //     setTimeout(hideInputs, 200);
        // }






        // Method 1: Enhanced URL monitoring with multiple detection methods
        setupUrlMonitoring() {
            // Store original URL
            this.currentUrl = window.location.href;
            
            // Method 1a: Override history methods
            const originalPushState = history.pushState;
            const originalReplaceState = history.replaceState;
            
            history.pushState = (...args) => {
                originalPushState.apply(history, args);
                console.log('PushState detected');
                setTimeout(() => this.handleUrlChange(), 100);
            };
            
            history.replaceState = (...args) => {
                originalReplaceState.apply(history, args);
                console.log('ReplaceState detected');
                setTimeout(() => this.handleUrlChange(), 100);
            };
            
            // Method 1b: Listen for popstate (back/forward buttons)
            this.addEventListener(window, 'popstate', () => {
                console.log('Popstate detected');
                setTimeout(() => this.handleUrlChange(), 100);
            });
            
            // Method 1c: Periodic URL checking as fallback
            this.urlCheckInterval = setInterval(() => {
                if (window.location.href !== this.currentUrl) {
                    const oldUrl = this.currentUrl;
                    this.currentUrl = window.location.href;
                    console.log('Periodic check: URL changed from', oldUrl, 'to', this.currentUrl);
                    this.handleUrlChange();
                }
            }, 1000);
            
            // Method 1d: DOM mutation observer for dynamic content changes
            this.mutationObserver = new MutationObserver((mutations) => {
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
                    console.log('DOM navigation change detected');
                    setTimeout(() => this.handleUrlChange(), 200);
                }
            });
            
            this.mutationObserver.observe(document.body, {
                childList: true,
                subtree: true
            });
        }

        
         // Method 2: Handle URL changes and run your method
        handleUrlChange() {
            console.log('Handling URL change:', window.location.href);
            
            // Run your method every time
            const isWhatsAppInterface = this.isLipachatChatInterfaceView();
            
            if (isWhatsAppInterface) {
                console.log('WhatsApp interface detected - reinitializing');
                // Reinitialize if needed
                this.reinitializeForWhatsApp();
            } else {
                console.log('Not WhatsApp interface - cleaning up if needed');
                this.cleanupForNonWhatsApp();
            }
        }



        // Method 3: Enhanced interface detection
        isLipachatChatInterfaceView() {
            console.log('Checking if current page is WhatsApp interface...');
            
            // Check URL for lipachat.template
            const url = window.location.href;
            if (url.includes('model=whatsapp.chat') || url.includes('whatsapp.chat')) {
                console.log('Detected lipachat whatsapp interface via URL!!');
                return true;
            }
            
            // Check breadcrumbs or page title
            const breadcrumbs = document.querySelector('.breadcrumb');
            if (breadcrumbs && breadcrumbs.textContent.includes('WhatsApp Chat Interface')) {
                console.log('Detected lipachat whatsapp interface via breadcrumbs!!');
                return true;
            }
            
            // Additional checks for specific elements
            const whatsappElements = document.querySelector('.o_whatsapp_chat_interface') ||
                                document.querySelector('.chat-container') ||
                                document.querySelector('#chat-messages-container');
            
            if (whatsappElements) {
                console.log('Detected lipachat whatsapp interface via elements!!');
                return true;
            }
            
            console.log('No whatsapp interface detected!');
            return false;
        }



        // Method 4: Reinitialize when WhatsApp interface is detected
        reinitializeForWhatsApp() {
            // if (this.isInitialized) {
            //     console.log('Already initialized for WhatsApp');
            //     return;
            // }
            
            console.log('Reinitializing for WhatsApp interface');
            // this.hideInputsOnLoad();
            
            // Reset initialization state
            this.isInitialized = false;
            this.initPromise = null;
            
            // Initialize again
            this.initialize().catch(error => {
                console.error("Failed to reinitialize WhatsApp Chat:", error);
            });
        }


        // Method 5: Cleanup when not on WhatsApp interface
        cleanupForNonWhatsApp() {
            if (this.autoRefreshInterval) {
                clearInterval(this.autoRefreshInterval);
                this.autoRefreshInterval = null;
            }
            
            // Reset selected contact
            this.currentSelectedPartnerId = null;
            this.currentSelectedContactName = null;
            this.lastMessageId = 0;
            
            console.log('Cleaned up for non-WhatsApp interface');
        }


        isLipachatChatInterfaceView() {
            // Check URL for lipachat.template
            const url = window.location.href;
            if (url.includes('model=whatsapp.chat') || url.includes('whatsapp.chat')) {
                console.log('Detected lipachat whatsapp interface!!');
                return true;
            }
            
            // Check breadcrumbs or page title
            const breadcrumbs = document.querySelector('.breadcrumb');
            if (breadcrumbs && breadcrumbs.textContent.includes('WhatsApp Chat Interface')) {
                console.log('Detected lipachat whatsapp interface!!');
                return true;
            }

            console.log('No whatsapp interface detected!');
            
            return false;
        }


        
        async _doInitialize() {
            console.log("WhatsApp Chat Client initializing...");
            
            if (!this.isLipachatChatInterfaceView()) {
                console.log('Not on WhatsApp interface - skipping initialization');
                return;
            }
        
            // this.hideInputsOnLoad();
        
            // Start all async operations in parallel immediately
            const preloadPromise = this.preloadRecentContact();
            const contactsPromise = this.updateContactsList();
            const templatesPromise = this.loadTemplates();
            
            // Setup event delegation (works even before contacts are loaded)
            this.addEventListener(document, 'click', (event) => {
                const contactItem = event.target.closest('.contact-item');
                if (contactItem) {
                    event.preventDefault();
                    event.stopPropagation();
                    
                    const partnerId = contactItem.dataset.partnerId || 
                                     contactItem.getAttribute('data-partner-id');
                    const contactName = contactItem.dataset.contactName || 
                                      contactItem.getAttribute('data-contact-name') ||
                                      contactItem.querySelector('strong')?.textContent.trim() || 
                                      `Contact ${partnerId}`;
                    
                    if (partnerId && !isNaN(parseInt(partnerId))) {
                        this.selectContact(parseInt(partnerId), contactName);
                    }
                }
            });
        
            // Setup send button
            this.addEventListener(document, 'click', (event) => {
                if (event.target.matches('.o_whatsapp_send_button') || 
                    event.target.closest('.o_whatsapp_send_button')) {
                    event.preventDefault();
                    event.stopPropagation();
                    this.handleSendMessage();
                }
            });


            this.addEventListener(document, 'click', (event) => {
                if (event.target.matches('.o_whatsapp_send_template_button_v2') || 
                    event.target.closest('.o_whatsapp_send_template_button_v2')) {
                    event.preventDefault();
                    event.stopPropagation();
                    this.handleSendTemplate();
                }
            });
        
            // Setup message input with minimal waiting
            this.setupMessageInput();
            this.setupTemplateSelection();

            // Wait for preload to complete
            await Promise.all([preloadPromise, contactsPromise]);
            await Promise.all([preloadPromise, contactsPromise, templatesPromise]);


            // const normalInput = document.getElementById('normal-message-input');
            // const templateSection = document.getElementById('template-message-btn');

            // if (normalInput) {
            //     normalInput.style.display = 'none';
            // }
            // if (templateSection) {
            //     templateSection.style.display = 'none';
            // }

            // this.updateInputFields({ active: false }, false);
        
            this.startAutoRefresh();
            this.isInitialized = true;
            console.log("WhatsApp Chat Client initialized successfully");
        }

         
        async preloadRecentContact() {
            try {
                // Check for initial data in DOM
                const initialDataEl = document.querySelector('.o_chat_initial_data');
                if (initialDataEl && initialDataEl.dataset.initialData) {
                    const initialData = JSON.parse(initialDataEl.dataset.initialData);
                    
                    if (initialData.partner_id) {
                        // We have everything we need - update UI immediately
                        this.currentSelectedPartnerId = initialData.partner_id;
                        this.currentSelectedContactName = initialData.partner_name;
                        this.updateOdooFields(initialData.partner_id, initialData.partner_name);
                        this.updateChatHeader(initialData.partner_name);
                        
                        // Render pre-loaded content
                        const contactsContainer = document.querySelector('.chat-contacts .contacts-list') ||
                                                document.querySelector('.o_whatsapp_contacts_html');
                        if (contactsContainer && initialData.contacts_html) {
                            contactsContainer.innerHTML = initialData.contacts_html;
                        }
                        
                        if (initialData.messages_html) {
                            this.renderMessages(initialData.messages_html);
                        }
                        
                        return; // We're done
                    }
                }
                
                // Fallback to RPC if no initial data
                const result = await this.makeRpcCall('whatsapp.chat', 'get_most_recent_contact', []);
                if (result && result.partner_id) {
                    await this.selectContact(result.partner_id, result.name);
                }
            } catch (error) {
                console.error("Error preloading recent contact:", error);
            }
        }


        destroy() {

            this.stopSessionTimer();

            if (this.autoRefreshInterval) {
                clearInterval(this.autoRefreshInterval);
                this.autoRefreshInterval = null;
            }


            // Stop URL monitoring
            if (this.urlCheckInterval) {
                clearInterval(this.urlCheckInterval);
                this.urlCheckInterval = null;
            }

            if (this.mutationObserver) {
                this.mutationObserver.disconnect();
                this.mutationObserver = null;
            }

            
            this.eventListeners.forEach(({ element, event, handler }) => {
                element.removeEventListener(event, handler);
            });
            this.eventListeners = [];
            
            this.isInitialized = false;
            this.initPromise = null;
        }
    }

    // Global instance
    let whatsappChatClient = null;
    let initializationAttempted = false;

    function initializeWhatsAppChat() {
        // if (initializationAttempted) return;
        // initializationAttempted = true;
        
        if (whatsappChatClient) {
            whatsappChatClient.destroy();
        }
        
        whatsappChatClient = new WhatsAppChatClient();

        whatsappChatClient.setupUrlMonitoring();

        whatsappChatClient.handleUrlChange();

        // whatsappChatClient.initialize().catch(error => {
        //     console.error("Failed to initialize WhatsApp Chat:", error);
        //     initializationAttempted = false;
        // });
    }


    // Initialize as soon as possible
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeWhatsAppChat);
    } else {
        // DOM is already ready, initialize immediately
        setTimeout(initializeWhatsAppChat, 0);
    }

    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        if (whatsappChatClient) {
            whatsappChatClient.destroy();
        }
    });

    // Expose to global scope
    window.WhatsAppChatClient = WhatsAppChatClient;
    window.initializeWhatsAppChat = initializeWhatsAppChat;
    window.whatsappChatClient = whatsappChatClient;

})();