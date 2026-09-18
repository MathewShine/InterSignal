import { motion } from "motion/react";

function getGreeting(hour) {
  if (hour < 12) return "Good morning.";
  if (hour < 17) return "Good afternoon.";
  return "Good evening.";
}

export function HomeGreeting({ hour = new Date().getHours() }) {
  return (
    <motion.header animate={{ opacity: 1, y: 0 }} className="home-greeting" initial={{ opacity: 0, y: 6 }} transition={{ delay: .1, duration: .28 }}>
      <div>
        <h1>Overview</h1>
        <p>Market, portfolio and research at a glance.</p>
      </div>
      <p className="home-greeting__salutation">{getGreeting(hour)} Shine</p>
    </motion.header>
  );
}
