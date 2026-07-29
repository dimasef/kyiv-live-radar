import { LogOut, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

import { isAdminRole } from "@/api";
import Avatar from "@/components/common/Avatar";
import { ADMIN_PATH, navigate } from "@/router";
import { useRadar } from "@/store";

import ContactsSection from "./ContactsSection";

const PROVIDER_LABEL: Record<string, string> = {
  password: "Пошта + пароль",
  google: "Google",
  telegram: "Telegram",
};

const ROLE_BADGE: Record<string, { label: string; cls: string; shield: boolean }> = {
  admin_g: { label: "Дівчина Адміна", cls: "bg-pink-400/15 text-pink-300", shield: true },
  admin: { label: "Адміністратор", cls: "bg-phosphor/15 text-phosphor-soft", shield: true },
  user: { label: "Користувач", cls: "bg-white/5 text-slate-400", shield: false },
};

/** Signed-in user's account page: profile header, contacts, linked sign-in
 * methods, admin tools link, and sign-out — one consistent section rhythm. */
export default function AccountPage() {
  const user = useRadar((s) => s.user);
  const status = useRadar((s) => s.authStatus);
  const logout = useRadar((s) => s.logout);

  if (status !== "authed" || !user) {
    return (
      <div className="flex h-full items-center justify-center bg-ink-950 text-sm text-slate-400">
        {status === "unknown" ? "Завантаження…" : "Ви не увійшли."}
      </div>
    );
  }

  const role = ROLE_BADGE[user.role] ?? ROLE_BADGE.user;
  const isAdmin = isAdminRole(user.role);

  return (
    <div className="h-full overflow-y-auto bg-ink-950 px-4 py-8 text-slate-200">
      <div className="mx-auto max-w-md">
        <header className="flex items-center gap-4">
          <Avatar
            name={user.display_name || user.email || "Акаунт"}
            avatarUrl={user.avatar_url}
            size={56}
          />
          <div className="min-w-0 flex-1">
            <h1 className="truncate font-display text-lg font-bold text-slate-100">
              {user.display_name || user.email || "Акаунт"}
            </h1>
            {user.email && <p className="truncate text-xs text-slate-500">{user.email}</p>}
            <span
              className={`mt-1.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${role.cls}`}
            >
              {role.shield && <ShieldCheck size={11} />}
              {role.label}
            </span>
          </div>
        </header>

        {isAdmin && (
          <button
            onClick={() => navigate(ADMIN_PATH)}
            className="mt-5 flex w-full items-center justify-center gap-2 rounded-lg border border-phosphor/25 bg-phosphor/[0.06] px-4 py-2 text-sm text-phosphor-soft transition-colors hover:border-phosphor/40"
          >
            <ShieldCheck size={15} /> Відкрити адмінку
          </button>
        )}

        <Section title="Контакти">
          <ContactsSection />
        </Section>

        <Section title="Способи входу">
          <div className="flex flex-wrap gap-2">
            {user.providers.map((p) => (
              <span
                key={p}
                className="rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1 text-xs text-slate-300"
              >
                {PROVIDER_LABEL[p] ?? p}
              </span>
            ))}
          </div>
        </Section>

        <button
          onClick={() => {
            logout();
            navigate("/");
          }}
          className="mt-8 flex w-full items-center justify-center gap-2 rounded-lg border border-red-400/25 bg-red-400/[0.05] px-4 py-2 text-sm text-red-300 transition-colors hover:border-red-400/40"
        >
          <LogOut size={15} /> Вийти
        </button>
      </div>
    </div>
  );
}

/** Uniform profile section: an Unbounded uppercase title + a hairline rule,
 * then its body — the single rhythm every block on the page shares. */
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-8 border-t border-white/[0.06] pt-5">
      <h2 className="panel-title mb-3">{title}</h2>
      {children}
    </section>
  );
}
