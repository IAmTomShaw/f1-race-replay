import YearCard from '@renderer/components/year-card'

export default function Home() {
  const years = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
  return (
    <>
      <h1>F1 Race Replay</h1>
      <p>
        A Python application for visualizing Formula 1 race telemetry and replaying race events with
        interactive controls and a graphical interface.
      </p>
      <div className="flex gap-5">
        {years.map((year) => {
          return <YearCard year={year} key={year} />
        })}
      </div>
    </>
  )
}
