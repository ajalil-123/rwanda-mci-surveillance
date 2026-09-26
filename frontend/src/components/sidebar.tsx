"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import {
  MapTrifold,
  Table,
  ChartLineUp,
  Calendar,
  ClipboardText,
  ShieldCheck,
  SignOut,
  User,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

const NAV = [
  {
    href: "/dashboard",
    label: "MCI Classification",
    desc: "Confirmed MCI incidents",
    icon: ClipboardText,
  },
  {
    href: "/dashboard/map",
    label: "Incident Map",
    desc: "Geographic view",
    icon: MapTrifold,
  },
  {
    href: "/dashboard/analytics",
    label: "Analytics",
    desc: "Hotspots · Tiers · CFR",
    icon: ChartLineUp,
  },
  {
    href: "/dashboard/trends",
    label: "Trends",
    desc: "Seasonal · Yearly · Heatmap",
    icon: Calendar,
  },
  {
    href: "/dashboard/explorer",
    label: "Data Explorer",
    desc: "Raw records + export",
    icon: Table,
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { data: session } = useSession();

  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col border-r border-border bg-muted/30">
      {/* Brand */}
      <div className="border-b border-border p-4">
        <div className="flex items-center gap-3">
          <ShieldCheck weight="fill" className="text-primary" size={24} />
          <div className="flex flex-col leading-tight">
            <span className="text-sm font-semibold">NHIC</span>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Surveillance
            </span>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto p-3">
        <div className="mb-2 px-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Views
        </div>
        <ul className="space-y-1">
          {NAV.map((item) => {
            const active =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    "flex items-start gap-3 rounded-md px-3 py-2 text-sm transition",
                    active
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  <Icon size={18} weight={active ? "fill" : "regular"} className="mt-0.5 shrink-0" />
                  <span className="flex flex-col leading-tight">
                    <span className="font-medium">{item.label}</span>
                    <span className="text-[10px] text-muted-foreground">
                      {item.desc}
                    </span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* User footer */}
      <div className="border-t border-border p-3">
        <div className="flex items-center gap-3 rounded-md px-2 py-2">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
            <User size={16} weight="fill" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium truncate">
              {session?.user?.name || "Signed in"}
            </div>
            <div className="text-[10px] text-muted-foreground truncate">
              {session?.user?.email}
            </div>
          </div>
          <button
            onClick={() => signOut({ callbackUrl: "/" })}
            className="rounded-md p-2 text-muted-foreground hover:bg-muted hover:text-foreground transition"
            title="Sign out"
          >
            <SignOut size={16} />
          </button>
        </div>
      </div>
    </aside>
  );
}
