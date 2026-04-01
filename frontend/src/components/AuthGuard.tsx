import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { supabase } from "@/integrations/supabase/client";
import type { User } from "@supabase/supabase-js";

interface AuthGuardProps {
  children: (user: User) => React.ReactNode;
}

export default function AuthGuard({ children }: AuthGuardProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const [user, setUser] = useState<User | null | undefined>(undefined); // undefined = loading

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      const sessionUser = data.session?.user ?? null;
      setUser(sessionUser);
      if (sessionUser) {
        // Log the user id for debugging in devtools
        // eslint-disable-next-line no-console
        console.log("auth: user id", sessionUser.id);
      }
      if (!sessionUser) {
        navigate("/auth", { replace: true });
      }
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      const sessionUser = session?.user ?? null;
      setUser(sessionUser);
      if (sessionUser) {
        // Log the user id when auth state changes (e.g., sign in)
        // eslint-disable-next-line no-console
        console.log("auth: user id", sessionUser.id);
      }
      if (!sessionUser) {
        navigate("/auth", { replace: true });
      }
    });

    return () => subscription.unsubscribe();
  }, [navigate, location.pathname]);

  if (user === undefined) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#f5f5f7]">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-apple-divider border-t-apple-blue" />
      </div>
    );
  }

  if (!user) return null;

  return <>{children(user)}</>;
}
