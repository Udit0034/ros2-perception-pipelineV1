// ============================================================================
// Drivable Area Node — extracts a binary mask of drivable regions from the
// colored segmentation image.
//
// Subscribes : /perception/segmentation   (sensor_msgs/Image, BGR8 colored mask)
// Publishes  : /perception/drivable_area  (sensor_msgs/Image, mono8 binary mask)
//
// Color mapping is loaded at runtime from a CSV (default: label_colors.csv).
// The node will look for common drivable class names such as `Road` and
// `RoadLine` in the CSV and use their colors. If the CSV cannot be read,
// it falls back to built-in CamVid drivable colors.
// ============================================================================

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <cv_bridge/cv_bridge.h>
#include <opencv2/opencv.hpp>
#include <filesystem>
#include <vector>
#include <string>
#include <fstream>
#include <sstream>
#include <map>
#include <algorithm>
#include <cctype>

class DrivableAreaNode : public rclcpp::Node
{
public:
    DrivableAreaNode() : Node("drivable_area_node")
    {
        // ── Load class colors from CSV (default: label_colors.csv) ──────
        std::string class_dict_path = this->declare_parameter<std::string>(
            "class_dict_path", "label_colors.csv");
        output_path_ = this->declare_parameter<std::string>(
            "output_path", "/data/output/drivable_area_output.mp4");

        // Ensure output directory exists
        try {
            std::filesystem::path out_dir = std::filesystem::path(output_path_).parent_path();
            if (!out_dir.empty() && !std::filesystem::exists(out_dir)) {
                std::filesystem::create_directories(out_dir);
            }
        } catch (const std::exception &e) {
            RCLCPP_WARN(this->get_logger(), "Could not create output directory: %s", e.what());
        }

        RCLCPP_INFO(this->get_logger(), "Loading class colors from %s", class_dict_path.c_str());

        std::map<std::string, cv::Vec3b> color_map; // name -> BGR
        std::ifstream ifs(class_dict_path);
        if (ifs.is_open()) {
            std::string line;
            // Read header
            std::getline(ifs, line);
            while (std::getline(ifs, line)) {
                if (line.empty()) continue;
                std::stringstream ss(line);
                std::string id_s, name, r_s, g_s, b_s;
                if (!std::getline(ss, id_s, ',')) continue;
                if (!std::getline(ss, name, ',')) continue;
                if (!std::getline(ss, r_s, ',')) continue;
                if (!std::getline(ss, g_s, ',')) continue;
                if (!std::getline(ss, b_s, ',')) continue;

                auto trim = [](std::string s) {
                    s.erase(s.begin(), std::find_if(s.begin(), s.end(), [](unsigned char ch){ return !std::isspace(ch); }));
                    s.erase(std::find_if(s.rbegin(), s.rend(), [](unsigned char ch){ return !std::isspace(ch); }).base(), s.end());
                    return s;
                };

                std::string name_t = trim(name);
                try {
                    int r = std::stoi(trim(r_s));
                    int g = std::stoi(trim(g_s));
                    int b = std::stoi(trim(b_s));
                    // store as BGR for OpenCV
                    color_map[name_t] = cv::Vec3b((uint8_t)b, (uint8_t)g, (uint8_t)r);
                } catch (...) {
                    // skip malformed lines
                    continue;
                }
            }
        } else {
            RCLCPP_WARN(this->get_logger(), "Could not open %s — falling back to defaults", class_dict_path.c_str());
        }

        // Preferred drivable class names (will pick those that exist in CSV)
        std::vector<std::string> preferred = {"Road", "RoadLine", "LaneMkgsDriv", "RoadShoulder"};
        for (const auto &n : preferred) {
            auto it = color_map.find(n);
            if (it != color_map.end()) drivable_colors_.push_back(it->second);
        }

        // If CSV did not provide any, fall back to original CamVid BGR values
        if (drivable_colors_.empty()) {
            drivable_colors_.push_back(cv::Vec3b(128,  64, 128));  // Road
            drivable_colors_.push_back(cv::Vec3b(192,   0, 128));  // LaneMkgsDriv
            drivable_colors_.push_back(cv::Vec3b(192, 128, 128));  // RoadShoulder
            RCLCPP_INFO(this->get_logger(), "Using built-in drivable color defaults.");
        } else {
            RCLCPP_INFO(this->get_logger(), "Loaded %zu drivable colors from %s", drivable_colors_.size(), class_dict_path.c_str());
        }

        // ── Subscriber ─────────────────────────────────────────────────────
        subscription_ = this->create_subscription<sensor_msgs::msg::Image>(
            "/perception/segmentation", 100,
            std::bind(&DrivableAreaNode::segmentation_callback, this,
                      std::placeholders::_1));

        // ── Publisher ──────────────────────────────────────────────────────
        publisher_ = this->create_publisher<sensor_msgs::msg::Image>(
            "/perception/drivable_area", 10);

        RCLCPP_INFO(this->get_logger(),
                     "Drivable area node ready — waiting for segmentation...");
    }

    ~DrivableAreaNode()
    {
        if (video_writer_.isOpened()) {
            video_writer_.release();
            RCLCPP_INFO(this->get_logger(), "Drivable area video saved.");
        }
    }

private:
    void segmentation_callback(const sensor_msgs::msg::Image::SharedPtr msg)
    {
        // Convert ROS Image → OpenCV BGR image
        cv_bridge::CvImagePtr cv_ptr;
        try {
            cv_ptr = cv_bridge::toCvCopy(msg, "bgr8");
        } catch (cv_bridge::Exception &e) {
            RCLCPP_ERROR(this->get_logger(), "cv_bridge error: %s", e.what());
            return;
        }

        cv::Mat seg_image = cv_ptr->image;

        // ── Create binary mask (white = drivable, black = not) ─────────
        cv::Mat drivable_mask = cv::Mat::zeros(seg_image.rows, seg_image.cols, CV_8UC1);

        for (const auto &color : drivable_colors_)
        {
            // Create a mask for this specific color
            cv::Mat color_mask;
            cv::inRange(seg_image, color, color, color_mask);

            // OR it into the combined drivable mask
            cv::bitwise_or(drivable_mask, color_mask, drivable_mask);
        }

        // ── Write drivable mask to video file ─────────────────────────
        if (!video_writer_.isOpened()) {
            int fourcc = cv::VideoWriter::fourcc('m','p','4','v');
            video_writer_.open(output_path_, fourcc, 10.0,
                               cv::Size(drivable_mask.cols, drivable_mask.rows), false);
            RCLCPP_INFO(this->get_logger(), "Saving drivable area video to %s", output_path_.c_str());
        }
        video_writer_.write(drivable_mask);

        // Publish as mono8 image
        auto out_msg = cv_bridge::CvImage(
            msg->header, "mono8", drivable_mask).toImageMsg();

        publisher_->publish(*out_msg);
    }

    // ── Member variables ───────────────────────────────────────────────────
    std::vector<cv::Vec3b> drivable_colors_;
    rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr subscription_;
    rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr publisher_;
    cv::VideoWriter video_writer_;
    std::string output_path_;
};

// ── Main ───────────────────────────────────────────────────────────────────
int main(int argc, char *argv[])
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<DrivableAreaNode>());
    rclcpp::shutdown();
    return 0;
}
