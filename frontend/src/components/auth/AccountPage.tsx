import { LogOut, ShieldCheck } from "lucide-react";

import { isAdminRole } from "@/api";
import { ADMIN_PATH, navigate } from "@/router";
import { useRadar } from "@/store";

const PROVIDER_LABEL: Record<string, string> = {
  password: "Пошта + пароль",
  google: "Google",
  telegram: "Telegram",
};

/** Signed-in user's account page: profile, linked sign-in methods, admin tools
 * link, and sign-out. */
export default function AccountPage() {
  const user = useRadar((s) => s.user);
  const status = useRadar((s) => s.authStatus);
  const logout = useRadar((s) => s.logout);

  if (status !== "authed" || !user) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 bg-ink-950 text-slate-300">
        <p className="text-sm text-slate-400">
          {status === "unknown" ? "Завантаження…" : "Ви не увійшли."}
        </p>
      </div>
    );
  }

  // 'admin_g' is a manual admin variant — same access as 'admin', shown pink.
  const roleBadge =
    user.role === "admin_g"
      ? { label: "Дівчина Адміна", cls: "bg-pink-400/15 text-pink-300", shield: true }
      : user.role === "admin"
        ? { label: "Адміністратор", cls: "bg-phosphor/15 text-phosphor-soft", shield: true }
        : { label: "Користувач", cls: "bg-white/5 text-slate-400", shield: false };

  return (
    <div className="h-full overflow-y-auto bg-ink-950 px-4 py-8 text-slate-200">
      <div className="mx-auto max-w-md">
        <div className="flex items-center gap-3">
          {user.avatar_url && (
            <img src={user.avatar_url} alt="" className="h-14 w-14 rounded-full" />
          )}
          <div className="min-w-0">
            <h1 className="truncate font-display text-lg font-bold text-slate-100">
              {user.display_name || user.email || "Акаунт"}
            </h1>
            {user.email && <p className="truncate text-xs text-slate-500">{user.email}</p>}
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ${roleBadge.cls}`}
          >
            {roleBadge.shield && <ShieldCheck size={12} />}
            {roleBadge.label}
          </span>
        </div>

        {isAdminRole(user.role) && (
          <button
            onClick={() => navigate(ADMIN_PATH)}
            className="mt-4 flex items-center gap-2 rounded-lg border border-phosphor/25 bg-phosphor/[0.06] px-4 py-2 text-sm text-phosphor-soft hover:border-phosphor/40"
          >
            <ShieldCheck size={15} /> Відкрити адмінку
          </button>
        )}

        <div className="mt-6">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Способи входу
          </h2>
          <div className="mt-2 flex flex-wrap gap-2">
            {user.providers.map((p) => (
              <span
                key={p}
                className="rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1 text-xs text-slate-300"
              >
                {PROVIDER_LABEL[p] ?? p}
              </span>
            ))}
          </div>
        </div>

        <button
          onClick={() => {
            logout();
            navigate("/");
          }}
          className="mt-8 flex items-center gap-2 rounded-lg border border-red-400/25 bg-red-400/[0.05] px-4 py-2 text-sm text-red-300 hover:border-red-400/40"
        >
          <LogOut size={15} /> Вийти
        </button>
      </div>
    </div>
  );
}
