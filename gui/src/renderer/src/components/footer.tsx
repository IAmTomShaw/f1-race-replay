import githubLogo from '../assets/images/github-mark-white.svg'

export default function Footer(): React.JSX.Element {
  return (
    <footer>
      <a href="https://github.com/IAmTomShaw/f1-race-replay" target="_blank" rel="noreferrer">
        <img alt="Github Logo" src={githubLogo} className="w-7"></img>
      </a>
    </footer>
  )
}
