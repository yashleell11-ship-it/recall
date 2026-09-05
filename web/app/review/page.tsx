import { Suspense } from "react";
import { ReviewSession, ReviewSkeleton } from "./ReviewSession";

export const metadata = { title: "Review · Recall" };

export default function ReviewPage() {
  return (
    <Suspense fallback={<ReviewSkeleton />}>
      <ReviewSession />
    </Suspense>
  );
}
