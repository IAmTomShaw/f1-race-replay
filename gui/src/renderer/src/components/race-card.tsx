interface RaceCardProps {
  RoundNumber: number
  Country: string
  Location: string
  OfficialEventName: string
}

export default function RaceCard({
  RoundNumber,
  Country,
  // Location,
  OfficialEventName
}: RaceCardProps): React.ReactElement {
  return (
    <>
      <span className="event font-bold text-2xl">{Country}</span>
      <span className="event official-name">{OfficialEventName}</span>
      <span className="event round-number">Round {RoundNumber}</span>
    </>
  )
}
