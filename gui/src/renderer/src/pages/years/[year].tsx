import 'slick-carousel/slick/slick.css'
import 'slick-carousel/slick/slick-theme.css'
import { useParams, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import RaceCard from '../../components/race-card'
import Slider from 'react-slick'
import { ToastContainer, toast } from 'react-toastify'

interface Race {
  RoundNumber: number
  Country: string
  Location: string
  OfficialEventName: string
}

declare global {
  interface Window {
    api: {
      runGetSchedule: (args: { year: number }) => void
      onPythonOutput: (callback: (data: string) => void) => void
      readData: (callback: (data: Race[]) => void) => void
      runRaceReplay: (args: { year: number; round: number }) => void
    }
  }
}

export default function Year(): React.ReactElement {
  const navigate = useNavigate()
  const { year } = useParams()
  const [scheduleData, setScheduleData] = useState<Race[] | null>(null)

  const goBack = (): void => {
    navigate('/')
  }

  function startRaceReplay(round: number): void {
    toast.info(
      'Loading replay for round ' +
        round +
        '. Press F12 to open devtools console to see progress. It may take a few mins to load.',
      {
        position: 'bottom-right',
        autoClose: 5000,
        hideProgressBar: false,
        closeOnClick: false,
        pauseOnHover: false,
        draggable: false,
        progress: undefined,
        theme: 'dark'
      }
    )
    window.api.runRaceReplay({ year: Number(year), round: round })
    window.api.onPythonOutput((data) => {
      console.log(`Python Output: ${data}`)
    })
  }

  useEffect(() => {
    if (!year) return

    window.api.runGetSchedule({ year: Number(year) })

    window.api.onPythonOutput((data) => {
      console.log(`Python Output: ${data}`)
    })

    window.api.readData((data) => {
      setScheduleData(data)
    })
  }, [year])

  const settings = {
    centerMode: true,
    infinite: true,
    centerPadding: '60px',
    slidesToShow: 3,
    speed: 500,
    rows: 3,
    slidesPerRow: 1,
    draggable: false,
    initialSlide: 1
  }

  return (
    <>
      <h1>Year: {year}</h1>
      <button onClick={goBack}>Back</button>
      <div className="w-[95%] m-0">
        {scheduleData && (
          <Slider {...settings}>
            {scheduleData.map((race, index) => (
              <div key={index}>
                <button
                  className="card w-[300px] h-[150px]"
                  onClick={() => startRaceReplay(race.RoundNumber)}
                >
                  <RaceCard
                    RoundNumber={race.RoundNumber}
                    Country={race.Country}
                    Location={race.Location}
                    OfficialEventName={race.OfficialEventName}
                  />
                </button>
              </div>
            ))}
          </Slider>
        )}
      </div>
      <ToastContainer
        position="bottom-right"
        autoClose={5000}
        hideProgressBar={false}
        newestOnTop={false}
        closeOnClick={false}
        rtl={false}
        pauseOnFocusLoss={false}
        draggable={false}
        pauseOnHover={false}
        theme="dark"
      />
    </>
  )
}
