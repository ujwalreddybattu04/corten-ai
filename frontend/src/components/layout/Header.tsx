import Link from "next/link";
import { BRAND_NAME, SITE_TITLE } from "@/config/constants";

export default function Header() {
    return (
        <header className="header" id="main-header">
            <div className="header-left">
                <Link href="/" className="header-logo">
                    <img src="/logo.svg" alt={SITE_TITLE} width={32} height={32} />
                    <span className="header-brand">{BRAND_NAME}</span>
                </Link>
            </div>
            <div className="header-center">
                {/* Compact SearchBar for inner pages */}
            </div>
            <div className="header-right">
                {/* Avatar */}
            </div>
        </header>
    );
}
