// /** @odoo-module **/

// import { NavBar } from "@web/webclient/navbar/navbar";
// import { patch } from "@web/core/utils/patch";

// patch(NavBar.prototype, {
//     /**
//      * Override menu click to force reload
//      */
//     async onMenuClick(menu, ev) {
//         // Call the original method first
//         await super.onMenuClick(...arguments);
        
//         // Check if this is one of your specific menus that should force reload
//         const menuIds = [
//             'lipachat_odoo_ex.menu_lipachat_config',
//             'lipachat_odoo_ex.menu_lipachat_messages',
//             'lipachat_odoo_ex.menu_lipachat_templates',
//             'lipachat_odoo_ex.menu_whatsapp_chat_interface'
//         ];
        
//         if (menuIds.includes(menu.xmlid)) {
//             // Force a hard reload of the page
//             window.location.reload();
//         }
//     },
// });