from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import requests
import json
import logging
import re
import base64
import mimetypes

_logger = logging.getLogger(__name__)

class LipachatTemplate(models.Model):
    _name = 'lipachat.template'
    _description = 'WhatsApp Message Templates'
    _rec_name = 'name'

    name = fields.Char('Template Name', required=True)
    language = fields.Selection(
        selection=[('en', 'English')],
        string='Language',
        default='en',
        required=True,
        readonly=True
    )
    category = fields.Selection([
        ('MARKETING', 'Marketing'),
        ('UTILITY', 'Utility'),
        ('AUTHENTICATION', 'Authentication')
    ], 'Category', required=True, default='UTILITY')
    
    phone_number = fields.Char('Phone Number', required=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], 'Status', default='draft', readonly=True)
    
    # Header components
    header_type = fields.Selection([
        ('TEXT', 'Text'),
        ('IMAGE', 'Image'),
        ('VIDEO', 'Video'),
        ('DOCUMENT', 'Document')
    ], 'Header Type')
    header_text = fields.Char('Header Text')
    header_example = fields.Char('Header Example', help="Example value for variables like {{1}}")
    header_media_id = fields.Char('Media ID', help="Media ID from WhatsApp Business API", readonly=True)
    header_media = fields.Binary('Media File', help="Upload media file for header")
    header_media_filename = fields.Char('Media Filename')
    is_uploading_media = fields.Boolean('Uploading Media', default=False)
    upload_status = fields.Selection([
        ('none', 'No Upload'),
        ('uploading', 'Uploading...'),
        ('success', 'Upload Successful'),
        ('error', 'Upload Failed')
    ], 'Upload Status', default='none')
    upload_error_message = fields.Text('Upload Error Message')
    
    # Body component
    body_text = fields.Text('Body Text', required=True)
    body_examples = fields.Text('Body Examples (JSON)', help="JSON array of example values for variables like {{1}}, {{2}}")
    
    # Footer component (optional)
    footer_text = fields.Char('Footer Text')
    
    # Authentication specific fields
    add_security_recommendation = fields.Boolean('Add Security Recommendation', 
                                                help="For AUTHENTICATION category only")
    code_expiration_minutes = fields.Integer('Code Expiration (Minutes)', 
                                           help="For AUTHENTICATION category only", default=10)
    
    # Buttons (optional, max 3)
    button_1_type = fields.Selection([
        ('QUICK_REPLY', 'Quick Reply'),
        ('URL', 'URL'),
        ('PHONE_NUMBER', 'Phone Number'),
        ('OTP', 'OTP (Authentication only)')
    ], 'Button 1 Type')
    button_1_text = fields.Char('Button 1 Text')
    button_1_url = fields.Char('Button 1 URL')
    button_1_url_example = fields.Char('Button 1 URL Example')
    button_1_phone_number = fields.Char('Button 1 Phone Number')
    button_1_phone_example = fields.Char('Button 1 Phone Example')
    button_1_otp_type = fields.Selection([
        ('COPY_CODE', 'Copy Code'),
        ('ONE_TAP', 'One Tap')
    ], 'OTP Type', default='COPY_CODE')
    
    button_2_type = fields.Selection([
        ('QUICK_REPLY', 'Quick Reply'),
        ('URL', 'URL'),
        ('PHONE_NUMBER', 'Phone Number'),
        ('OTP', 'OTP (Authentication only)')
    ], 'Button 2 Type')
    button_2_text = fields.Char('Button 2 Text')
    button_2_url = fields.Char('Button 2 URL')
    button_2_url_example = fields.Char('Button 2 URL Example')
    button_2_phone_number = fields.Char('Button 2 Phone Number')
    button_2_phone_example = fields.Char('Button 2 Phone Example')
    button_2_otp_type = fields.Selection([
        ('COPY_CODE', 'Copy Code'),
        ('ONE_TAP', 'One Tap')
    ], 'OTP Type', default='COPY_CODE')
    
    button_3_type = fields.Selection([
        ('QUICK_REPLY', 'Quick Reply'),
        ('URL', 'URL'),
        ('PHONE_NUMBER', 'Phone Number'),
        ('OTP', 'OTP (Authentication only)')
    ], 'Button 3 Type')
    button_3_text = fields.Char('Button 3 Text')
    button_3_url = fields.Char('Button 3 URL')
    button_3_url_example = fields.Char('Button 3 URL Example')
    button_3_phone_number = fields.Char('Button 3 Phone Number')
    button_3_phone_example = fields.Char('Button 3 Phone Example')
    button_3_otp_type = fields.Selection([
        ('COPY_CODE', 'Copy Code'),
        ('ONE_TAP', 'One Tap')
    ], 'OTP Type', default='COPY_CODE')
    
    component_data = fields.Text('Component Data (JSON)', compute='_compute_component_data', store=True)
    
    @api.onchange('header_media', 'header_media_filename')
    def _onchange_header_media(self):
        """Auto-upload media when file is selected - improved version"""
        if self.header_media and self.header_media_filename and not self.header_media_id:
            # Reset previous status
            self.upload_status = 'uploading'
            self.upload_error_message = False
            self.is_uploading_media = True
            
            # Validate file type based on header type
            if self.header_type and not self._validate_media_type():
                self.upload_status = 'error'
                self.upload_error_message = f'Invalid file type for {self.header_type} header. Please select an appropriate file.'
                self.is_uploading_media = False
                return
            
            # Check file size limits
            try:
                file_data = base64.b64decode(self.header_media)
                file_size_mb = len(file_data) / (1024 * 1024)
                
                # Check size limits based on header type
                size_limits = {
                    'IMAGE': 5,     # 5MB for images
                    'VIDEO': 16,    # 16MB for videos  
                    'DOCUMENT': 100 # 100MB for documents
                }
                
                max_size = size_limits.get(self.header_type, 5)
                if file_size_mb > max_size:
                    self.upload_status = 'error'
                    self.upload_error_message = f'File size ({file_size_mb:.1f}MB) exceeds limit of {max_size}MB for {self.header_type} files.'
                    self.is_uploading_media = False
                    return
                    
            except Exception as e:
                self.upload_status = 'error'
                self.upload_error_message = f'Error processing file: {str(e)}'
                self.is_uploading_media = False
                return
            
            # Perform upload
            try:
                self._perform_media_upload()
                # Upload was successful - no need to return notification here
                # as the UI will show the success status
            except ValidationError as ve:
                self.upload_status = 'error'
                error_msg = str(ve)
                # Clean up the error message
                if error_msg.startswith('ValidationError\n\n'):
                    error_msg = error_msg.replace('ValidationError\n\n', '')
                self.upload_error_message = error_msg.replace('\n', ' ').strip()
                self.is_uploading_media = False
                _logger.error(f'Media upload failed: {ve}')
            except Exception as e:
                self.upload_status = 'error'
                self.upload_error_message = f'Unexpected error: {str(e)}'
                self.is_uploading_media = False
                _logger.error(f'Unexpected media upload error: {e}', exc_info=True)

    
    def _validate_media_type(self):
        """Enhanced media type validation"""
        if not self.header_media_filename:
            return False
            
        mime_type, _ = mimetypes.guess_type(self.header_media_filename)
        filename_lower = self.header_media_filename.lower()
        
        if self.header_type == 'IMAGE':
            # Check both MIME type and file extension
            valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
            return (mime_type and mime_type.startswith('image/')) or \
                any(filename_lower.endswith(ext) for ext in valid_extensions)
        elif self.header_type == 'VIDEO':
            valid_extensions = ['.mp4', '.3gp', '.3gpp']
            return (mime_type and mime_type.startswith('video/')) or \
                any(filename_lower.endswith(ext) for ext in valid_extensions)
        elif self.header_type == 'DOCUMENT':
            valid_extensions = ['.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.ppt', '.pptx']
            return (mime_type and (mime_type.startswith(('application/', 'text/')))) or \
                any(filename_lower.endswith(ext) for ext in valid_extensions)
        
        return True
    
    def _perform_media_upload(self):
        """Perform the actual media upload with proper file handling"""
        if not self.header_media:
            raise ValidationError(_('No media file selected'))
        
        config = self.env['lipachat.config'].get_active_config()
        if not config or not config.api_key or not config.api_base_url:
            raise ValidationError(_('API configuration is missing or incomplete'))
        
        try:
            # Decode base64 file data
            file_data = base64.b64decode(self.header_media)
            file_name = self.header_media_filename or 'media_file'
            file_size = len(file_data)
            file_size_mb = file_size / (1024 * 1024)  # Size in MB
            
            _logger.info("=== Preparing upload request ===")
            _logger.info(f"File: {file_name}")
            _logger.info(f"Size: {file_size} bytes ({file_size_mb:.2f} MB)")
            _logger.info(f"Header type: {self.header_type}")
            
            # Get MIME type
            mime_type, _ = mimetypes.guess_type(file_name)
            if not mime_type:
                mime_type = 'application/octet-stream'
            
            # Prepare the multipart form data
            files = {
                'file': (file_name, file_data, mime_type)
            }
            
            # Headers - DO NOT include Content-Type for multipart/form-data
            # requests library will set it automatically with boundary
            headers = {
                'apiKey': config.api_key,
                'Accept': 'application/json'
            }
            
            upload_url = f"{config.api_base_url.rstrip('/')}/template/upload/file"
            
            _logger.info("\n=== Request Details ===")
            _logger.info(f"URL: {upload_url}")
            _logger.info("Headers:")
            for k, v in headers.items():
                _logger.info(f"  {k}: {v}")
            _logger.info("Files:")
            _logger.info(f"  Filename: {file_name}")
            _logger.info(f"  MIME type: {mime_type}")
            _logger.info(f"  Data size: {file_size} bytes")
            
            # Send the request with proper timeout
            _logger.info("\nSending upload request...")
            response = requests.post(
                upload_url,
                headers=headers,
                files=files,
                timeout=(30, 120)  # 30s connection timeout, 120s read timeout for large files
            )
            
            _logger.info("\n=== Response Details ===")
            _logger.info(f"Status Code: {response.status_code}")
            _logger.info("Response Headers:")
            for k, v in response.headers.items():
                _logger.info(f"  {k}: {v}")
            _logger.info(f"Response Content: {response.text}")
            
            # Handle the response
            if response.status_code != 200:
                _logger.error(f"HTTP Error: {response.status_code} - {response.text}")
                raise ValidationError(_('Upload failed with status %s: %s') % (response.status_code, response.text))
            
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                _logger.error(f"Invalid JSON response: {response.text}")
                raise ValidationError(_('Invalid server response format'))
            
            _logger.info("\n=== Response Data ===")
            _logger.info(f"Status: {response_data.get('status')}")
            _logger.info(f"Message: {response_data.get('message')}")
            _logger.info(f"Data: {response_data.get('data')}")
            if response_data.get('errors'):
                _logger.warning(f"Errors: {response_data.get('errors')}")
            
            # Check for successful response
            if response_data.get('status') == 'success' and response_data.get('data'):
                self.header_media_id = response_data['data']
                self.upload_status = 'success'
                self.upload_error_message = False
                _logger.info("\n=== Upload Successful ===")
                _logger.info(f"Media ID: {self.header_media_id}")
                return True
            
            # Handle API-specific error cases
            error_msg = response_data.get('message', 'Unknown error from API')
            if response_data.get('errors'):
                if isinstance(response_data['errors'], dict):
                    error_details = ', '.join([f"{k}: {v}" for k, v in response_data['errors'].items()])
                elif isinstance(response_data['errors'], list):
                    error_details = ', '.join(str(e) for e in response_data['errors'])
                else:
                    error_details = str(response_data['errors'])
                error_msg += f" (Details: {error_details})"
            
            _logger.error("\n=== Upload Failed ===")
            _logger.error(f"API Error: {error_msg}")
            raise ValidationError(_('API reported error: %s') % error_msg)
            
        except requests.exceptions.Timeout:
            _logger.error("\n=== Timeout Error ===")
            _logger.error("Request timed out")
            raise ValidationError(_('Upload timed out. Please try again or check your connection.'))
        except requests.exceptions.ConnectionError:
            _logger.error("\n=== Connection Error ===")
            _logger.error("Could not connect to server")
            raise ValidationError(_('Could not connect to upload server. Please check your network connection.'))
        except requests.exceptions.RequestException as re:
            _logger.error("\n=== Network Error ===")
            _logger.error(f"Type: {type(re).__name__}")
            _logger.error(f"Message: {str(re)}")
            raise ValidationError(_('Network error during upload: %s') % str(re))
        except ValidationError:
            # Re-raise validation errors as-is
            raise
        except Exception as e:
            _logger.error("\n=== Unexpected Error ===")
            _logger.error(f"Type: {type(e).__name__}")
            _logger.error(f"Message: {str(e)}", exc_info=True)
            raise ValidationError(_('Unexpected upload error: %s') % str(e))
        finally:
            self.is_uploading_media = False
            _logger.info("=== Upload process completed ===")
    
    def clear_media(self):
        """Clear uploaded media and allow new upload"""
        self.header_media = False
        self.header_media_filename = False
        self.header_media_id = False
        self.upload_status = 'none'
        self.upload_error_message = False
        self.is_uploading_media = False
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Media cleared. You can now upload a new file.'),
                'type': 'success',
            }
        }
    
    def retry_upload(self):
        """Retry failed upload"""
        if self.header_media and self.header_media_filename:
            self.upload_status = 'uploading'
            self.upload_error_message = False
            self.is_uploading_media = True
            
            try:
                self._perform_media_upload()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Media uploaded successfully! Media ID: %s') % self.header_media_id,
                        'type': 'success',
                    }
                }
            except ValidationError as ve:
                self.upload_status = 'error'
                self.upload_error_message = str(ve).replace('ValidationError\n\n', '').replace('\n', ' ')
                self.is_uploading_media = False
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Upload Failed'),
                        'message': self.upload_error_message,
                        'type': 'danger',
                    }
                }
            except Exception as e:
                self.upload_status = 'error'
                self.upload_error_message = f'Unexpected error: {str(e)}'
                self.is_uploading_media = False
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Upload Failed'),
                        'message': self.upload_error_message,
                        'type': 'danger',
                    }
                }

    @api.depends('header_type', 'header_text', 'header_example', 'header_media_id',
                'body_text', 'body_examples', 'footer_text', 'category',
                'add_security_recommendation', 'code_expiration_minutes',
                'button_1_text', 'button_1_type', 'button_1_url', 'button_1_url_example',
                'button_1_phone_number', 'button_1_phone_example', 'button_1_otp_type',
                'button_2_text', 'button_2_type', 'button_2_url', 'button_2_url_example',
                'button_2_phone_number', 'button_2_phone_example', 'button_2_otp_type',
                'button_3_text', 'button_3_type', 'button_3_url', 'button_3_url_example',
                'button_3_phone_number', 'button_3_phone_example', 'button_3_otp_type')
    def _compute_component_data(self):
        """Compute component data JSON matching API format"""
        for record in self:
            component = {}
            
            # Header
            if record.header_type and (record.header_text or record.header_media_id):
                header_data = {'format': record.header_type}
                
                if record.header_type == 'TEXT' and record.header_text:
                    header_data['text'] = record.header_text
                    if record.header_example:
                        header_data['example'] = record.header_example
                elif record.header_media_id:
                    header_data['mediaId'] = record.header_media_id
                
                component['header'] = header_data
            
            # Body
            if record.category == 'AUTHENTICATION':
                # Special handling for authentication templates
                body_data = {}
                if record.add_security_recommendation:
                    body_data['addSecurityRecommendation'] = True
                component['body'] = body_data
            else:
                # Regular body handling
                body_data = {'text': record.body_text}
                
                # Add examples if body contains variables
                if record.body_examples and re.search(r'\{\{[0-9]+\}\}', record.body_text):
                    try:
                        examples = json.loads(record.body_examples)
                        if isinstance(examples, list):
                            body_data['examples'] = examples
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                component['body'] = body_data
            
            # Footer
            if record.category == 'AUTHENTICATION' and record.code_expiration_minutes:
                component['footer'] = {'codeExpirationMinutes': record.code_expiration_minutes}
            elif record.footer_text:
                component['footer'] = {'text': record.footer_text}
            
            # Buttons
            buttons = []
            for i in range(1, 4):
                button_text = getattr(record, f'button_{i}_text')
                button_type = getattr(record, f'button_{i}_type')
                
                if button_text and button_type:
                    button_data = {
                        'type': button_type,
                        'text': button_text
                    }
                    
                    if button_type == 'URL':
                        button_url = getattr(record, f'button_{i}_url')
                        if button_url:
                            button_data['url'] = button_url
                            
                        button_url_example = getattr(record, f'button_{i}_url_example')
                        if button_url_example:
                            button_data['example'] = button_url_example
                            
                    elif button_type == 'PHONE_NUMBER':
                        button_phone = getattr(record, f'button_{i}_phone_number')
                        if button_phone:
                            button_data['phoneNumber'] = button_phone
                            
                        button_phone_example = getattr(record, f'button_{i}_phone_example')
                        if button_phone_example:
                            button_data['example'] = button_phone_example
                            
                    elif button_type == 'OTP':
                        button_otp_type = getattr(record, f'button_{i}_otp_type')
                        if button_otp_type:
                            button_data['otpType'] = button_otp_type
                    
                    buttons.append(button_data)
            
            if buttons:
                component['buttons'] = buttons
            
            record.component_data = json.dumps(component, indent=2)
    
    def _extract_variables_from_text(self, text):
        """Extract variable placeholders from text like {{1}}, {{2}}"""
        if not text:
            return []
        return re.findall(r'\{\{([0-9]+)\}\}', text)
    
    @api.constrains('body_examples', 'body_text')
    def _check_body_examples(self):
        """Validate that examples match the variables in body text"""
        for record in self:
            if record.body_examples and record.body_text:
                variables = record._extract_variables_from_text(record.body_text)
                if variables:
                    try:
                        examples = json.loads(record.body_examples)
                        if not isinstance(examples, list):
                            raise ValidationError(_('Body examples must be a JSON array'))
                        
                        max_var = max([int(v) for v in variables])
                        if len(examples) < max_var:
                            raise ValidationError(
                                _('Body examples must have at least %d items for variables %s') % 
                                (max_var, ', '.join([f'{{{{{v}}}}}' for v in variables]))
                            )
                    except (json.JSONDecodeError, ValueError):
                        raise ValidationError(_('Body examples must be valid JSON array'))
    
    @api.constrains('category', 'button_1_type', 'button_2_type', 'button_3_type')
    def _check_authentication_buttons(self):
        """Validate OTP buttons are only used with AUTHENTICATION category"""
        for record in self:
            otp_buttons = [
                record.button_1_type == 'OTP',
                record.button_2_type == 'OTP', 
                record.button_3_type == 'OTP'
            ]
            
            if any(otp_buttons) and record.category != 'AUTHENTICATION':
                raise ValidationError(_('OTP buttons can only be used with AUTHENTICATION category'))
    
    @api.constrains('header_type', 'header_media_id')
    def _check_media_requirements(self):
        """Validate media requirements for non-text headers"""
        for record in self:
            if record.header_type and record.header_type != 'TEXT' and not record.header_media_id:
                raise ValidationError(_('Media ID is required for %s header type. Please upload media first.') % record.header_type)
    
    def create_template(self):
        """Create template via API"""
        config = self.env['lipachat.config'].get_active_config()
        
        headers = {
            'apiKey': config.api_key,
            'Content-Type': 'application/json'
        }
        
        data = {
            'name': self.name,
            'language': self.language,
            'category': self.category,
            'component': json.loads(self.component_data)
        }
        
        try:
            response = requests.post(
                f"{config.api_base_url}/template/{self.phone_number}",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                self.status = 'submitted'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Template created successfully!'),
                        'type': 'success',
                    }
                }
            else:
                error_msg = response.text
                try:
                    error_data = response.json()
                    if 'message' in error_data:
                        error_msg = error_data['message']
                except:
                    pass
                raise ValidationError(_('Failed to create template: %s') % error_msg)
                
        except requests.RequestException as e:
            raise ValidationError(_('Connection error: %s') % str(e))