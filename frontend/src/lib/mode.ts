/**
 * Read-only build (VITE_READONLY=1): the public site published to Cloudflare Pages. Data comes from
 * static JSON files exported by backend/tools/export_static.py and management UI is hidden.
 */
export const READONLY = import.meta.env.VITE_READONLY === "1";
