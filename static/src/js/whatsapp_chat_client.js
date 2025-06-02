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
        
                const messagesHtml = await this.makeRpcCall(
                    'whatsapp.chat',
                    'rpc_get_messages_html',
                    [partnerId]
                );
                this.renderMessages(messagesHtml);
        
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

        // OPTIMIZED: Initialize with minimal DOM dependency
        async initialize() {
            if (this.isInitialized || this.initPromise) {
                return this.initPromise;
            }

            this.initPromise = this._doInitialize();
            return this.initPromise;
        }

        async _doInitialize() {
            console.log("WhatsApp Chat Client initializing...");
        
            // Start all async operations in parallel immediately
            const preloadPromise = this.preloadRecentContact();
            const contactsPromise = this.updateContactsList();
            
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
        
            // Setup message input with minimal waiting
            this.setupMessageInput();
        
            // Wait for preload to complete
            await Promise.all([preloadPromise, contactsPromise]);
        
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
            if (this.autoRefreshInterval) {
                clearInterval(this.autoRefreshInterval);
                this.autoRefreshInterval = null;
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
        if (initializationAttempted) return;
        initializationAttempted = true;
        
        if (whatsappChatClient) {
            whatsappChatClient.destroy();
        }
        
        whatsappChatClient = new WhatsAppChatClient();
        whatsappChatClient.initialize().catch(error => {
            console.error("Failed to initialize WhatsApp Chat:", error);
            initializationAttempted = false;
        });
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