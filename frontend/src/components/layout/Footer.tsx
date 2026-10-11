import { BRAND_NAME } from "@/config/constants";

export default function Footer() {
    return (
        <footer className="footer" id="main-footer">
            <p>&copy; {new Date().getFullYear()} {BRAND_NAME} AI. All rights reserved.</p>
        </footer>
    );
}
