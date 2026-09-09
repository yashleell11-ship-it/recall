"use client";

import { useCallback } from "react";
import { useToast } from "@/components/rich";

/**
 * The exact command that writes a lesson, selectable and copyable.
 *
 * There is no "Write this lesson" button anywhere on this screen, and no
 * disabled-looking one either. The shell prefetches on route intent, so any
 * control that could turn a hover into a paid POST is the failure that rule
 * exists to prevent — and the daily cap is a dollar, with no resume path, so
 * a mis-click could burn a real fraction of a day's budget on a request the
 * browser would time out on anyway. Copying text spends nothing.
 */
export function CommandBlock({ command }: { command: string }) {
  const toast = useToast();

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(command);
      toast("Command copied");
    } catch {
      // No clipboard permission, or an insecure origin. The text is
      // `select-all`, so the fallback is already on screen.
      toast("Could not copy — select the command instead", {
        variant: "error",
      });
    }
  }, [command, toast]);

  return (
    <div className="mt-3 panel px-3 py-2.5 flex items-center gap-3 max-w-[46ch]">
      <code className="telemetry text-[12px] text-fg select-all flex-1 break-all">
        {command}
      </code>
      <button
        type="button"
        onClick={copy}
        className="label hover:text-fg-2 transition-colors duration-[90ms] shrink-0"
      >
        copy
      </button>
    </div>
  );
}
