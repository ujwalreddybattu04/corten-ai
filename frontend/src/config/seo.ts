import { SITE_TITLE, SITE_DESCRIPTION, SITE_URL } from "./constants";

export const SEO_CONFIG = {
    defaultTitle: `${SITE_TITLE} — AI-Powered Answer Engine`,
    titleTemplate: `%s | ${SITE_TITLE}`,
    description: SITE_DESCRIPTION,
    openGraph: {
        type: "website",
        siteName: SITE_TITLE,
        url: SITE_URL,
    },
    twitter: {
        cardType: "summary_large_image",
    },
};
