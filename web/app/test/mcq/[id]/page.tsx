import { notFound } from "next/navigation";
import { McqSession } from "./McqSession";

export const metadata = { title: "Yash Made Test · Recall" };

export default async function McqAttemptPage({
  params,
}: PageProps<"/test/mcq/[id]">) {
  const { id } = await params;
  const attemptId = Number(id);
  // Anything can be typed into the address bar; an attempt id is an integer.
  if (!Number.isInteger(attemptId) || attemptId <= 0) notFound();
  return <McqSession id={attemptId} />;
}
