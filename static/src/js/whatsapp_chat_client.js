// static/src/js/whatsapp_chat_client.js
// Vanilla JavaScript version - no Odoo module dependencies

(function() {
    'use strict';

    // WhatsApp Chat Client Class
    class WhatsAppChatClient {
        constructor() {
            this.currentSelectedPartnerId = null;
            this.currentSelectedContactName = null;
            this.autoRefreshInterval = null;
            this.lastMessageId = 0;
        }

        // Helper function to get CSRF token
        getCSRFToken() {
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
                            document.querySelector('input[name="csrf_token"]')?.value ||
                            odoo?.csrf_token;
            return csrfToken;
        }

        // Helper function to make RPC calls using fetch
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

        // Function to render messages HTML dynamically
        renderMessages(messagesHtml) {
            const messagesContainer = document.getElementById('chat-messages-container');
            if (messagesContainer) {
                messagesContainer.innerHTML = messagesHtml;
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            } else {
                console.warn("Messages container not found!");
            }
        }

        // Function to handle contact selection (client-side)
        async selectContact(partnerId, contactName) {
            // Validate input parameters
            if (!partnerId || isNaN(partnerId)) {
                console.error('Invalid partner ID:', partnerId);
                return;
            }
            
            if (!contactName || contactName === 'undefined') {
                console.warn('Contact name is undefined, using fallback');
                contactName = `Contact ${partnerId}`;
            }

            console.log(`Selecting contact: ${contactName} (ID: ${partnerId})`);

            // Update hidden Odoo fields directly
            const currentContactField = document.querySelector('input[name="contact"]');
            const currentPartnerIdField = document.querySelector('input[name="contact_partner_id"]');
            
            if (currentContactField) currentContactField.value = contactName;
            if (currentPartnerIdField) currentPartnerIdField.value = partnerId;

            // Update global state
            this.currentSelectedPartnerId = parseInt(partnerId);
            this.currentSelectedContactName = contactName;
            this.lastMessageId = 0;

            // Visually highlight selected contact
            document.querySelectorAll('.contact-item').forEach(function(item) {
                item.style.backgroundColor = 'white';
                item.style.border = '1px solid #eee';
                item.classList.remove('selected');
            });
            
            const selectedItem = document.querySelector(`.contact-item[data-partner-id="${partnerId}"]`);
            if (selectedItem) {
                selectedItem.style.backgroundColor = '#e8f5e8';
                selectedItem.style.border = '2px solid #25D366';
                selectedItem.classList.add('selected');
            }

            // Update the chat header with the selected contact's name
            const chatHeaderName = document.getElementById('chat-header-contact-name');
            if (chatHeaderName) {
                chatHeaderName.textContent = contactName;
            }

            // Fetch messages for the newly selected contact using RPC
            try {
                console.log('Fetching messages for partner ID:', partnerId);
                const messagesHtml = await this.makeRpcCall(
                    'whatsapp.chat',
                    'rpc_get_messages_html',
                    [parseInt(partnerId)],
                    {}
                );
                this.renderMessages(messagesHtml);
            } catch (error) {
                console.error("Error fetching messages via RPC:", error);
                this.renderMessages(`<div style="color: red; padding: 20px;">Error loading messages: ${error.message}<br>Please check console for details.</div>`);
            }
        }

        // Function to send message via RPC
        async sendMessage(recordId) {
            const messageInput = document.querySelector('textarea[name="new_message"]');
            const messageText = messageInput ? messageInput.value.trim() : '';

            if (!this.currentSelectedPartnerId || !messageText) {
                console.warn("No contact selected or message is empty.");
                // Show user-friendly message
                const messagesContainer = document.getElementById('chat-messages-container');
                if (messagesContainer && !messageText) {
                    const tempMsg = document.createElement('div');
                    tempMsg.style.cssText = 'color: orange; padding: 10px; text-align: center; font-style: italic;';
                    tempMsg.textContent = 'Please enter a message';
                    messagesContainer.appendChild(tempMsg);
                    setTimeout(() => tempMsg.remove(), 3000);
                }
                return;
            }

            // Show sending indicator
            const sendButton = document.querySelector('.o_whatsapp_send_button');
            const originalButtonText = sendButton ? sendButton.textContent : '';
            if (sendButton) {
                sendButton.textContent = 'Sending...';
                sendButton.disabled = true;
            }

            try {
                await this.makeRpcCall(
                    'whatsapp.chat',
                    'send_message',
                    [recordId],
                    {
                        new_message: messageText,
                        contact_partner_id: this.currentSelectedPartnerId,
                    }
                );

                // Clear the input field
                if (messageInput) messageInput.value = '';

                // After sending, immediately refresh the chat area for the current contact
                await this.selectContact(this.currentSelectedPartnerId, this.currentSelectedContactName);

                // Optionally, refresh contacts list as well
                await this.updateContactsList();

            } catch (error) {
                console.error("Error sending message via RPC:", error);
                // Show user-friendly error message
                const messagesContainer = document.getElementById('chat-messages-container');
                if (messagesContainer) {
                    const errorMsg = document.createElement('div');
                    errorMsg.style.cssText = 'color: red; padding: 10px; text-align: center; background: #ffebee; border-radius: 4px; margin: 10px;';
                    errorMsg.textContent = `Failed to send message: ${error.message || 'Unknown error'}`;
                    messagesContainer.appendChild(errorMsg);
                    setTimeout(() => errorMsg.remove(), 5000);
                }
            } finally {
                // Restore button state
                if (sendButton) {
                    sendButton.textContent = originalButtonText;
                    sendButton.disabled = false;
                }
            }
        }

        // Function to update the contacts list (left panel)
        async updateContactsList() {
            console.log("Updating contacts list...");
            try {
                const contactsHtml = await this.makeRpcCall(
                    'whatsapp.chat',
                    'rpc_get_contacts_html',
                    [],
                    {}
                );
                
                const contactsContainer = document.querySelector('.chat-contacts .contacts-list');
                if (contactsContainer) {
                    contactsContainer.innerHTML = contactsHtml;
                    // Re-attach click listeners to new contact items
                    this.attachContactClickListeners();
                    // Re-apply selection highlight after list update
                    if (this.currentSelectedPartnerId) {
                        const selectedItem = document.querySelector(`.contact-item[data-partner-id="${this.currentSelectedPartnerId}"]`);
                        if (selectedItem) {
                            selectedItem.style.backgroundColor = '#e8f5e8';
                            selectedItem.style.border = '2px solid #25D366';
                            selectedItem.classList.add('selected');
                        }
                    }
                }
            } catch (error) {
                console.error("Error updating contacts list:", error);
            }
        }

        // Auto-refresh functionality for the chat and contacts
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
            }, 10000); // 10 seconds
        }

        // Function to attach click listeners to contact items
        attachContactClickListeners() {
            console.log('Attaching contact click listeners...');
            document.querySelectorAll('.contact-item').forEach(item => {
                // Debug: log what data attributes are available
                console.log('Contact item data:', {
                    partnerId: item.dataset.partnerId,
                    contactName: item.dataset.contactName,
                    innerHTML: item.innerHTML.substring(0, 100) + '...'
                });

                // Remove existing listener to prevent duplicates
                const newItem = item.cloneNode(true);
                item.parentNode.replaceChild(newItem, item);
                
                // Add new listener
                newItem.addEventListener('click', (event) => {
                    event.preventDefault();
                    
                    // Get data from the clicked element
                    const partnerId = event.currentTarget.dataset.partnerId || 
                                    event.currentTarget.getAttribute('data-partner-id');
                    const contactName = event.currentTarget.dataset.contactName || 
                                      event.currentTarget.getAttribute('data-contact-name') ||
                                      event.currentTarget.textContent.trim();
                    
                    console.log('Contact clicked:', { partnerId, contactName });
                    
                    if (partnerId && !isNaN(partnerId)) {
                        this.selectContact(parseInt(partnerId), contactName);
                    } else {
                        console.error('Invalid contact data:', { partnerId, contactName });
                        alert('Invalid contact data. Please refresh the page.');
                    }
                });
            });
        }

        // Main initialization function
        async initialize() {
            console.log("WhatsApp Chat Client JS Initializing...");

            // Get initial selected contact from hidden fields if already set by Python
            const initialPartnerIdField = document.querySelector('input[name="contact_partner_id"]');
            const initialContactNameField = document.querySelector('input[name="contact"]');

            if (initialPartnerIdField && initialPartnerIdField.value) {
                this.currentSelectedPartnerId = parseInt(initialPartnerIdField.value);
                this.currentSelectedContactName = initialContactNameField ? initialContactNameField.value : '';
                await this.selectContact(this.currentSelectedPartnerId, this.currentSelectedContactName);
            }

            // Attach event listener for sending messages
            const sendMessageButton = document.querySelector('.o_whatsapp_send_button');
            if (sendMessageButton) {
                // Try multiple ways to get the record ID
                let currentRecordId = this.getCurrentRecordId();

                sendMessageButton.addEventListener('click', (event) => {
                    event.preventDefault();
                    // Re-check record ID in case it changed
                    currentRecordId = this.getCurrentRecordId();
                    if (currentRecordId) {
                        this.sendMessage(currentRecordId);
                    } else {
                        console.error("Could not find current record ID to send message.");
                        alert("Error: Chat session not properly initialized. Please refresh the page.");
                    }
                });
            }

            // Also handle Enter key in message input
            const messageInput = document.querySelector('textarea[name="new_message"]');
            if (messageInput) {
                messageInput.addEventListener('keydown', (event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        sendMessageButton && sendMessageButton.click();
                    }
                });
            }

            // Attach click listeners to all contact items
            this.attachContactClickListeners();

            // Start auto-refresh
            this.startAutoRefresh();

            // Ensure proper scrolling on initial load
            setTimeout(() => {
                const messagesContainer = document.getElementById('chat-messages-container');
                if (messagesContainer) {
                    messagesContainer.scrollTop = messagesContainer.scrollHeight;
                }
            }, 300);
        }

        // Helper function to get current record ID
        getCurrentRecordId() {
            // Method 1: From URL hash
            let recordIdMatch = window.location.hash.match(/id=(\d+)/);
            if (recordIdMatch) {
                return parseInt(recordIdMatch[1]);
            }
            
            // Method 2: From URL pathname
            recordIdMatch = window.location.pathname.match(/\/(\d+)(?:\/|$)/);
            if (recordIdMatch) {
                return parseInt(recordIdMatch[1]);
            }
            
            // Method 3: From a hidden field or data attribute
            const recordIdField = document.querySelector('input[name="id"]');
            if (recordIdField && recordIdField.value) {
                return parseInt(recordIdField.value);
            }

            // Method 4: From URL search params
            const urlParams = new URLSearchParams(window.location.search);
            const idParam = urlParams.get('id');
            if (idParam) {
                return parseInt(idParam);
            }

            return null;
        }

        // Cleanup function
        destroy() {
            if (this.autoRefreshInterval) {
                clearInterval(this.autoRefreshInterval);
                this.autoRefreshInterval = null;
            }
        }
    }

    // Global instance
    let whatsappChatClient = null;

    // Initialize function
    function initializeWhatsAppChat() {
        // Avoid multiple initializations
        if (whatsappChatClient) {
            whatsappChatClient.destroy();
        }
        
        whatsappChatClient = new WhatsAppChatClient();
        whatsappChatClient.initialize().catch(error => {
            console.error("Failed to initialize WhatsApp Chat:", error);
        });
    }

    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        if (whatsappChatClient) {
            whatsappChatClient.destroy();
        }
    });

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeWhatsAppChat);
    } else {
        // DOM is already ready
        setTimeout(initializeWhatsAppChat, 100);
    }

    // Also try to initialize after a short delay for Odoo's dynamic content
    setTimeout(initializeWhatsAppChat, 1000);

    // Listen for Odoo's custom events
    document.addEventListener('DOMContentLoaded', initializeWhatsAppChat);

    // Expose to global scope for debugging
    window.WhatsAppChatClient = WhatsAppChatClient;
    window.initializeWhatsAppChat = initializeWhatsAppChat;

})();