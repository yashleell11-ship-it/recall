import { Suspense } from "react";
import { ReviewSession } from "./ReviewSession";

export const metadata = { title: "Review · Recall" };

export default function ReviewPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-dvh flex items-center justify-center">
          <p className="text-[13px] text-fg-3">Building the queue&hellip;</p>
        </div>
      }
    >
      <ReviewSession />
    </Suspense>
  );
}
