/**
 * Centralized branding constants for Corten AI.
 * Ensures zero-hardcoding and world-class maintainability.
 */

export const BRAND_NAME = "Corten";
export const COMPANY_NAME = "Chryselys Private Limited";
export const SITE_TITLE = `${BRAND_NAME} AI`;
export const SITE_DESCRIPTION = `High-state AI answer engine powered by ${COMPANY_NAME}`;
export const SITE_URL = "https://corten.ai";

export const STORAGE_KEYS = {
    THREADS: `${BRAND_NAME.toLowerCase()}_threads`,
    PINNED_THREADS: `${BRAND_NAME.toLowerCase()}_pinned_threads`,
    PRIVATE_MODE: `${BRAND_NAME.toLowerCase()}_private_mode`,
};

export const EVENTS = {
    THREADS_UPDATED: `${BRAND_NAME.toLowerCase()}_threads_updated`,
    PRIVATE_MODE_CHANGED: `${BRAND_NAME.toLowerCase()}_private_mode_changed`,
};
