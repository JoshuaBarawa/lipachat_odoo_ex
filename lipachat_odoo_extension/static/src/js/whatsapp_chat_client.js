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
            this.sessionInfo ={};
            this.sessionTimerInterval = null;
            this.sessionEndCallback = null;
            this.currentUrl = window.location.href;
            this.urlCheckInterval = null;
            this.mutationObserver = null;

            this.lastSessionState = null;
            this.lastUIState = null;
            this.lastContactsState = null;
            this.isUpdatingUI = false;
            this.sessionCheckInProgress = false;
            this.forceContactReselection = false;
            this.debouncedUpdateInputFields = this.debounce(this.updateInputFields.bind(this), 100);

            this.autoSelectContact = false;

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

        async getSessionInfo(partnerId) {
            if (this.sessionCheckInProgress) {
                return this.lastSessionState; // Return cached state if check in progress
            }
    
            this.sessionCheckInProgress = true;
            try {
                const partner = await this.getPartnerDetails(partnerId);
                const sessionInfo = await this.makeRpcCall(
                    'whatsapp.chat',
                    'check_contact_active_session',
                    [partner.mobile || partner.phone, partner.mobile || partner.phone]
                );
                
                this.lastSessionState = sessionInfo;
                return sessionInfo;
            } finally {
                this.sessionCheckInProgress = false;
            }
        }

        async selectContact(partnerId, contactName) {
            try {
                partnerId = parseInt(partnerId);
                if (isNaN(partnerId)) {
                    console.error('Invalid partner ID:', partnerId);
                    return;
                }
                
                // Don't re-select if already selected (prevents flickering during auto-refresh)
                if (this.currentSelectedPartnerId === partnerId && !this.forceContactReselection) {
                    return;
                }
                
                this.currentSelectedPartnerId = partnerId;
                this.currentSelectedContactName = contactName || `Contact ${partnerId}`;
                this.lastMessageId = 0;
                
                this.updateContactSelectionUI(partnerId);
                this.updateChatHeader(this.currentSelectedContactName);
                this.updateOdooFields(partnerId, this.currentSelectedContactName);
    
                // Get session info using unified method
                const sessionInfo = await this.getSessionInfo(partnerId);
                this.updateInputFields(sessionInfo, partnerId);
    
                // Start session timer if active
                if (sessionInfo.session_active && sessionInfo.expires_at) {
                    this.startSessionTimer(sessionInfo.expires_at);
                } else {
                    this.stopSessionTimer();
                }
                
                // Load messages
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



        async getPartnerDetails(partnerId) {
            return await this.makeRpcCall(
                'res.partner',
                'read',
                [partnerId, ['name', 'mobile', 'phone']]
            ).then(results => results[0]);
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

                    this.showChatSuccess('Message sent successfully');
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
            const sendTemplateButton = document.querySelector('.o_whatsapp_send_template_button_v2');

            const sendingStyle = {
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center', 
                padding: '6px 12px',
                justifyContent: 'left'   
            };
            
            const defaultStyle = {
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center', 
                padding: '6px 12px',
                justifyContent: 'left'
            };

            
            if (sendButton) {
                Object.assign(sendButton.style, isSending ? sendingStyle : defaultStyle);
                sendButton.innerHTML = isSending 
                    ? '<i class="fa fa-spinner fa-spin" style="margin-right: 7px;"></i> Sending...' 
                    : '<i class="fa fa-paper-plane" style="margin-right: 7px;"></i> Send';
                sendButton.disabled = isSending;
            }
        
            if (sendTemplateButton) {
                Object.assign(sendTemplateButton.style, isSending ? sendingStyle : defaultStyle);
                sendTemplateButton.innerHTML = isSending 
                    ? '<i class="fa fa-spinner fa-spin" style="margin-right: 7px;"></i> Sending...' 
                    : '<i class="fa fa-paper-plane" style="margin-right: 7px;"></i> Send Template';
                sendTemplateButton.disabled = isSending;
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
                    
                    // Check if we have contacts after update
                    const hasContacts = contactsContainer.querySelector('.contact-item') !== null;
                    
                    // Restore selection UI if a contact was selected
                    if (this.currentSelectedPartnerId) {
                        this.updateContactSelectionUI(this.currentSelectedPartnerId);
                        // Update input fields for selected contact
                        const sessionInfo = await this.getSessionInfo(this.currentSelectedPartnerId);
                        this.updateInputFields(sessionInfo, this.currentSelectedPartnerId, hasContacts);
                    } else {
                        // No contact selected - show appropriate state
                        if (hasContacts) {
                            this.showEmptyMessageArea();
                        } else {
                            this.showNoContactsMessage();
                        }
                        this.updateInputFields({ session_active: false }, null, hasContacts);
                    }
                }
            } catch (error) {
                console.error("Error updating contacts list:", error);
                this.updateInputFields({ session_active: false }, null, false);
            }
        }




    startAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
        }

        this.autoRefreshInterval = setInterval(async () => {
            if (document.visibilityState === 'visible') {
                try {

                    // Always update contacts list
                    await this.updateContactsList();
                    
                    // Only refresh messages if a contact is selected
                    if (this.currentSelectedPartnerId) {
                        const messagesHtml = await this.makeRpcCall(
                            'whatsapp.chat',
                            'rpc_get_messages_html',
                            [this.currentSelectedPartnerId]
                        );
                        this.renderMessages(messagesHtml);
                        
                        // Check session status
                        const sessionInfo = await this.getSessionInfo(this.currentSelectedPartnerId);
                        if (sessionInfo && this.hasSessionStateChanged(sessionInfo)) {
                            this.updateInputFields(sessionInfo, this.currentSelectedPartnerId);
                            this.updateSessionUI(sessionInfo);
                        }
                    }
                } catch (error) {
                    console.error("Error during auto-refresh:", error);
                }
            }
        }, 10000);
    }


        async refreshMessagesOnly(partnerId) {
            try {
                // Get fresh messages
                const messagesHtml = await this.makeRpcCall(
                    'whatsapp.chat',
                    'rpc_get_messages_html',
                    [partnerId]
                );
                
                // Only update messages, don't touch input fields
                this.renderMessages(messagesHtml);
                
                // Check session status separately and only update if changed
                const sessionInfo = await this.getSessionInfo(partnerId);
                if (sessionInfo && this.hasSessionStateChanged(sessionInfo)) {
                    this.updateInputFields(sessionInfo, partnerId);
                    this.updateSessionUI(sessionInfo);
                }
            } catch (error) {
                console.error("Error refreshing messages:", error);
            }
        }

        hasSessionStateChanged(newSessionInfo) {
            if (!this.lastSessionState) return true;
            
            return (
                this.lastSessionState.session_active !== newSessionInfo.session_active ||
                this.lastSessionState.expires_at !== newSessionInfo.expires_at
            );
        }

        debounce(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
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


        updateInputFields(sessionInfo, partnerId, hasContacts = null) {
            if (!this.isInitialized) return;
    
            const hasContact = !!partnerId;
            const isSessionActive = sessionInfo?.session_active || false;
            
            // Check if contacts exist if not provided
            if (hasContacts === null) {
                hasContacts = document.querySelector('.contact-item') !== null;
            }
    
            const normalInput = document.getElementById('normal-message-input');
            const templateSection = document.querySelector('.template-message-group');
    
            // Case 1: No contacts available at all
            if (!hasContacts) {
                if (normalInput) normalInput.style.display = 'none';
                if (templateSection) templateSection.style.display = 'none';
                this.showNoContactsMessage();
                return;
            }
    
            // Case 2: Contact selected with active session
            if (hasContact && isSessionActive) {
                if (normalInput) normalInput.style.display = 'flex';
                if (templateSection) templateSection.style.display = 'none';
                return;
            }
    
            // Case 3: Contact selected but no active session
            if (hasContact && !isSessionActive) {
                if (normalInput) normalInput.style.display = 'none';
                if (templateSection) templateSection.style.display = 'block';
                return;
            }
    
            // Case 4: No contact selected but contacts exist
            if (!hasContact && hasContacts) {
                if (normalInput) normalInput.style.display = 'none';
                if (templateSection) templateSection.style.display = 'none'; // CHANGED: Hide template section too
                return;
            }
        }


        showNoContactsMessage() {
            const messagesContainer = document.getElementById('chat-messages-container');
            if (messagesContainer) {
                messagesContainer.innerHTML = `
                    <div class="no-contacts-state">
                        <div style="
                            display: flex;
                            flex-direction: column;
                            align-items: center;
                            justify-content: center;
                            height: 100%;
                            min-height: 300px;
                            color: #666;
                            text-align: center;
                            padding: 20px;
                        ">
                            <i class="fa fa-address-book-o" style="font-size: 48px; margin-bottom: 20px; color: #ccc;"></i>
                            <h3 style="margin: 0 0 10px 0; font-weight: normal;">No Contacts Found</h3>
                            <p style="margin: 0; font-size: 14px;">No WhatsApp contacts are available for messaging</p>
                        </div>
                    </div>
                `;
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


        startSessionTimer(expiresAt) {
            this.stopSessionTimer();
            
            const updateTimer = () => {
                const now = new Date();
                const expiration = new Date(expiresAt);
                const remainingSeconds = Math.max(0, Math.floor((expiration - now) / 1000));
                
                if (remainingSeconds <= 0) {
                    this.stopSessionTimer();
                    this.showChatInfo('Session has expired');
                    this.updateInputFields({ session_active: false }, this.currentSelectedPartnerId);
                    return;
                }
                
                this.updateTimerDisplay(remainingSeconds);
            };
            
            // Update immediately
            updateTimer();
            
            // Update every second
            this.sessionTimerInterval = setInterval(updateTimer, 1000);
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
                    // this.showChatSuccess(result.message);
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
            console.log('Reinitializing for WhatsApp interface');
            
            // Reset initialization state
            this.isInitialized = false;
            this.initPromise = null;
            
            // Clear any selected contact
            this.currentSelectedPartnerId = null;
            this.currentSelectedContactName = null;
            
            // Initialize again
            this.initialize().catch(error => {
                console.error("Failed to reinitialize WhatsApp Chat:", error);
            });
        }


        enableAutoContactSelection() {
            this.autoSelectContact = true;
        }
    
        disableAutoContactSelection() {
            this.autoSelectContact = false;
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



        setupEventListeners() {
            // Contact selection
            this.addEventListener(document, 'click', (event) => {
                const contactItem = event.target.closest('.contact-item');
                if (contactItem) {
                    event.preventDefault();
                    event.stopPropagation();
                    const partnerId = contactItem.dataset.partnerId;
                    const contactName = contactItem.dataset.contactName || `Contact ${partnerId}`;
                    if (partnerId) this.selectContact(partnerId, contactName);
                }
            });
        
            // Message sending
            this.addEventListener(document, 'click', (event) => {
                if (event.target.closest('.o_whatsapp_send_button')) {
                    event.preventDefault();
                    this.handleSendMessage();
                }
            });
        
            // Template sending
            this.addEventListener(document, 'click', (event) => {
                if (event.target.closest('.o_whatsapp_send_template_button_v2')) {
                    event.preventDefault();
                    this.handleSendTemplate();
                }
            });
        
            // Message input handling
            this.setupMessageInput();
            this.setupTemplateSelection();
        }


        showInitialState() {
            // Clear any selected contact state
            this.currentSelectedPartnerId = null;
            this.currentSelectedContactName = null;
            this.lastMessageId = 0;
    
            // Clear chat header
            this.updateChatHeader('Select a contact to start chatting');
    
            // Clear Odoo fields
            this.clearOdooFields();
    
            // Show empty message area with instruction
            this.showEmptyMessageArea();
    
            // Show appropriate input fields
            const hasContacts = document.querySelector('.contact-item') !== null;
            this.updateInputFields({ session_active: false }, null, hasContacts);
        }

        clearOdooFields() {
            const contactField = this.findOdooField('contact');
            if (contactField) {
                contactField.value = '';
                contactField.dispatchEvent(new Event('input', { bubbles: true }));
                contactField.dispatchEvent(new Event('change', { bubbles: true }));
            }
    
            const partnerIdField = this.findOdooField('contact_partner_id');
            if (partnerIdField) {
                partnerIdField.value = '';
                partnerIdField.dispatchEvent(new Event('input', { bubbles: true }));
                partnerIdField.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }


        showEmptyMessageArea() {
            const messagesContainer = document.getElementById('chat-messages-container');
            if (messagesContainer) {
                messagesContainer.innerHTML = `
                    <div class="empty-chat-state">
                        <div style="
                            display: flex;
                            flex-direction: column;
                            align-items: center;
                            justify-content: center;
                            height: 100%;
                            min-height: 300px;
                            color: #666;
                            text-align: center;
                            padding: 20px;
                        ">
                            <i class="fa fa-whatsapp" style="font-size: 48px; margin-bottom: 20px; color: #25D366;"></i>
                            <h3 style="margin: 0 0 10px 0; font-weight: normal;">Welcome to WhatsApp Chat</h3>
                            <p style="margin: 0; font-size: 14px;">Select a contact from the list to start messaging</p>
                        </div>
                    </div>
                `;
            }
        }


        
        async _doInitialize() {
            console.log("WhatsApp Chat Client initializing...");
            
            if (!this.isLipachatChatInterfaceView()) {
                console.log('Not on WhatsApp interface - skipping initialization');
                return;
            }
    
            this.showLoadingState(true);
    
            try {
                // Hide all inputs initially
                const normalInput = document.getElementById('normal-message-input');
                const templateSection = document.querySelector('.template-message-group');
                if (normalInput) normalInput.style.display = 'none';
                if (templateSection) templateSection.style.display = 'none';
    
                // CHANGED: Don't preload recent contact, just load contacts list
                await Promise.all([
                    this.updateContactsList(),
                    this.loadTemplates()
                ]);
    
                // Setup all event listeners
                this.setupEventListeners();
    
                // CHANGED: Show initial state with no contact selected
                this.showInitialState();
    
                this.startAutoRefresh();
                this.isInitialized = true;
                console.log("WhatsApp Chat Client initialized successfully");
            } catch (error) {
                console.error("Initialization failed:", error);
            } finally {
                this.showLoadingState(false);
            }
        }

        

         
        async preloadRecentContact() {
            try {
                console.log("Auto-contact selection disabled");
                return;

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