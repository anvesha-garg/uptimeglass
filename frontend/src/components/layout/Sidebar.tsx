import { cx } from "../../lib/cx";

export interface NavItem {
  id: string;
  label: string;
  href: string;
}

interface SidebarProps {
  items: NavItem[];
  currentId: string;
  className?: string;
}

export function Sidebar({ items, currentId, className }: SidebarProps) {
  return (
    <nav className={cx("glass", "sidebar", className)} aria-label="Main">
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <a
              href={item.href}
              className={cx("sidebar__link", item.id === currentId && "sidebar__link--active")}
              aria-current={item.id === currentId ? "page" : undefined}
            >
              {item.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
