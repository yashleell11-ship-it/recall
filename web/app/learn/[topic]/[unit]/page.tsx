import { notFound } from "next/navigation";
import { LessonReader } from "./LessonReader";

export const metadata = { title: "Lesson · Recall" };

export default async function LessonPage({
  params,
}: PageProps<"/learn/[topic]/[unit]">) {
  const { topic, unit } = await params;
  const n = Number(unit);
  // Anything can be typed into the address bar; a unit is the 1-based number
  // printed on a timetable. Everything else the server answers for — an
  // unknown topic is a 404 from the API, an out-of-range unit a 422.
  if (!Number.isInteger(n) || n <= 0) notFound();
  return <LessonReader topic={topic} unit={n} />;
}
